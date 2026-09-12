"""校园网感知与校园信息自动同步。

功能边界：
- 网络状态检测：探测校园站点与外网连通性，区分 已确认校园网 / 校园网内·外网未认证 /
  公网（示例大学站点公网也可达，默认无法确认是否校园网）/ 离线。若用户配置了
  internal_hosts（仅校内可达的地址，如认证页）或 public_cidrs（学校公网出口 IP 段），
  命中即升级为「已确认校园网」。
- 信息同步：定期抓取信息源列表页（默认示例大学机械工程学院的通知公告/新闻聚焦/科研动态，
  苏迪 Webplus CMS 的列表格式），解析出条目（标题/链接/日期）入库判重。
  列表页为公开页面，公网也能访问；配置仅内网可达的源（如教务/内网通知）同样支持，
  只在校园网环境能抓到。
- 需要登录的校内系统（教务成绩、个人借阅等）不做自动抓取：涉及账号密码，超出本模块
  「抓公开信息」的安全边界。

SSRF 边界（与 library._safe_url 一致：只抓公网）：
- 仅 http/https；解析后的目标 IP 拒绝环回（本机 8178 应用 / 8080 模型服务）、私有网段、
  链路本地（云元数据 169.254.169.254）、组播与保留段；重定向目标逐跳复检。
- 示例大学各站点（www/jw/lib/news/mech.example.edu.cn）均为公网 IP（203.0.113.x.x 教育网段），
  其中教务处等仅校园网内可达——可达性正好用作「确认在校园网」的探测信号。
- 信息源配置只能经本机 API（有 Origin 白名单守卫）修改，抓取上限：每源 2MB、10s、
  每轮最多 8 个源，后台线程串行。
"""
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

from . import db

UA = "StudyPilot/0.1 (local study assistant; campus info sync)"

_EXAMPLE_MECH = "http://mech.example.edu.cn"

DEFAULT_CFG = {
    "auto_sync": True,
    "interval_min": 30,           # 后台同步间隔（分钟）
    # 校园连通性探测主机（http，公网可达的校内站点）
    "campus_hosts": ["mech.example.edu.cn", "www.example.edu.cn"],
    # 仅校园网内可达的公网主机（校外实测连不上）：连通 → 确认在校园网内
    "internal_hosts": ["jw.example.edu.cn"],
    # 学校公网出口 IP 段（示例大学教育网段；注意新闻网 203.0.113.13.13 公网可达，不算校内专用信号）
    "public_cidrs": ["203.0.113.0.0/16"],
    "external_host": "www.baidu.com",
    # 信息源：id 全局唯一，url 为列表页/首页地址；学习相关度优先排序
    "sources": [
        # --- 考试与教务（四六级/计算机等级/期末安排/选课） ---
        {"id": "jw_notice", "name": "教务处·通知公告", "url": "http://jw.example.edu.cn/"},
        # --- 全校 ---
        {"id": "example_notice", "name": "学校·通知公告", "url": "http://www.example.edu.cn/635/list.htm"},
        {"id": "example_news", "name": "示例大学新闻网", "url": "http://news.example.edu.cn/"},
        {"id": "lib_notice", "name": "图书馆·资源动态", "url": "http://lib.example.edu.cn/zydt/list.htm"},
        # --- 学院 ---
        {"id": "mech_notice", "name": "机械学院·通知公告", "url": f"{_EXAMPLE_MECH}/11369/list.htm"},
        {"id": "mech_news", "name": "机械学院·新闻聚焦", "url": f"{_EXAMPLE_MECH}/11368/list.htm"},
        {"id": "mech_research", "name": "机械学院·科研动态", "url": f"{_EXAMPLE_MECH}/11412/list.htm"},
    ],
}

MAX_PAGE_BYTES = 2 * 1024 * 1024   # 单页限读 2MB（只取列表，不抓正文）
FETCH_TIMEOUT = 10
PROBE_TIMEOUT = 4
MAX_SOURCES = 8
MAX_ITEMS_PER_SOURCE = 30
DETECT_CACHE_SECONDS = 120

STATE_LABELS = {
    "campus": "校园网（已确认）",
    "campus_likely": "校园网内 · 外网未通（可能未认证）",
    "public": "公网 · 校内专用站点不可达",
    "offline": "网络不可用",
}

_detect_cache: dict = {"ts": 0.0, "result": None}
_detect_lock = threading.Lock()

# 苏迪 Webplus 文章页：/2026/0907/c11368a279226/page.htm；兼容 /info/…/1234.htm 等常见高校 CMS
_ARTICLE_HREF = re.compile(r"(?:\d{4}/\d{4}/c\d+a\d+|/info/\d+/\d+)[^\"']*\.htm", re.I)
# 校主页模板用单引号属性 + 点分日期（2026.09.03），学院模板用双引号 + 横线日期，都要兼容
_ANCHOR_RE = re.compile(r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
_DATE_RE = re.compile(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", re.I)
_TITLE_ATTR_RE = re.compile(r"title=[\"']([^\"']{4,200})[\"']")
# 卡片式锚点（整个卡片是一个 <a>）：标题在嵌套的标题容器里，其余是图片/序号/日期等杂讯
_TITLE_CONTAINER_RE = re.compile(
    r"<(?:div|span|p|h[1-6])[^>]*class=[\"'][^\"']*(?:title|tit)[^\"']*[\"'][^>]*>(.*?)</(?:div|span|p|h[1-6])>",
    re.S | re.I)
_TRAILING_DATE_RE = re.compile(r"\s*[\(（]?\d{4}[-./年]\d{1,2}[-./月]\d{1,2}日?[\)）]?\s*$")
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_title(inner_html: str, anchor_tag: str) -> str:
    """从锚点提取干净标题：嵌套标题容器 > title 属性 > 整段锚文本，并去掉尾部日期。"""
    for candidate in (
        _TITLE_CONTAINER_RE.search(inner_html) and _TITLE_CONTAINER_RE.search(inner_html).group(1),
        _TITLE_ATTR_RE.search(anchor_tag) and _TITLE_ATTR_RE.search(anchor_tag).group(1),
        inner_html,
    ):
        if not candidate:
            continue
        t = re.sub(r"\s+", " ", _TAG_RE.sub("", candidate)).strip()
        t = _TRAILING_DATE_RE.sub("", t).strip()
        if len(t) >= 4:
            return t
    return ""


# ---------- SSRF 校验（允许校园私网，阻断环回/链路本地/保留段） ----------

def _validate_url(url: str) -> str:
    """只允许抓公网 http/https：拒绝环回/私有/链路本地/保留段（与 library._safe_url 同一立场）。"""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise OSError(f"仅允许 http/https 地址: {url}")
    if p.hostname.lower() == "localhost" or p.hostname.lower().endswith((".local", ".internal")):
        raise OSError(f"禁止访问本机地址: {p.hostname}")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except OSError as e:
        raise OSError(f"域名解析失败: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # 环回会打到本机 FastAPI/模型服务，私有网段与链路本地覆盖内网和云元数据
        if (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise OSError(f"禁止访问私有/保留地址: {ip}")
    return url


def _strip_default_port(url: str) -> str:
    """示例大学 WAF 对显式默认端口的地址（https://host:443/…）返回 404，重定向前规范化掉。"""
    p = urllib.parse.urlsplit(url)
    try:
        port = p.port
    except ValueError:
        return url
    if port is None or (p.scheme, port) not in (("https", 443), ("http", 80)):
        return url
    netloc = p.hostname or ""
    if ":" in netloc:  # IPv6 字面量
        netloc = f"[{netloc}]"
    return p._replace(netloc=netloc).geturl()


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(_strip_default_port(newurl))
        return super().redirect_request(req, fp, code, msg, headers, _strip_default_port(newurl))


_opener = urllib.request.build_opener(_SafeRedirectHandler())


def _fetch(url: str, timeout: int = FETCH_TIMEOUT, max_bytes: int = MAX_PAGE_BYTES) -> bytes:
    """GET 并限读 max_bytes；目标地址先过 SSRF 校验（含重定向逐跳复检）。"""
    _validate_url(_strip_default_port(url))
    req = urllib.request.Request(_strip_default_port(url), headers={"User-Agent": UA})
    with _opener.open(req, timeout=timeout) as resp:
        return resp.read(max_bytes + 1)


# ---------- 配置（存 meta，含默认值合并与校验） ----------

def _raw_saved() -> dict:
    try:
        saved = json.loads(db.get_meta("campus_cfg") or "{}")
    except ValueError:
        saved = {}
    return saved if isinstance(saved, dict) else {}


def get_cfg() -> dict:
    saved = _raw_saved()
    cfg = {**DEFAULT_CFG, **{k: v for k, v in saved.items() if k in DEFAULT_CFG}}
    # 只保留默认源与用户新增源，字段补齐
    sources = []
    for s in cfg.get("sources") or []:
        if isinstance(s, dict) and s.get("id") and s.get("url"):
            sources.append({"id": str(s["id"])[:60], "name": str(s.get("name") or s["id"])[:60],
                            "url": str(s["url"])[:300]})
    cfg["sources"] = sources[:MAX_SOURCES]
    return cfg


def save_cfg(patch: dict) -> dict:
    """patch 里的键覆盖默认/已存值；持久化时只存「已存 ∪ 本次 patch」的键——
    默认层不落库，这样应用升级带来的新默认信息源/探测主机能自动生效。"""
    saved = _raw_saved()
    cfg = get_cfg()
    if "auto_sync" in patch:
        cfg["auto_sync"] = bool(patch["auto_sync"])
    if patch.get("interval_min") is not None:
        try:
            cfg["interval_min"] = max(5, min(int(patch["interval_min"]), 1440))
        except (TypeError, ValueError):
            raise ValueError("interval_min 必须是分钟数") from None
    for key in ("campus_hosts", "internal_hosts", "public_cidrs"):
        if key in patch and patch[key] is not None:
            if not isinstance(patch[key], list):
                raise ValueError(f"{key} 必须是列表")
            vals = [str(v).strip() for v in patch[key] if str(v).strip()]
            if key == "public_cidrs":
                for v in vals:
                    try:
                        ipaddress.ip_network(v, strict=False)
                    except ValueError:
                        raise ValueError(f"非法 CIDR: {v}") from None
            else:
                for v in vals:
                    if not urllib.parse.urlparse(v if "//" in v else "//" + v).hostname:
                        raise ValueError(f"非法主机名: {v}")
            cfg[key] = vals[:10]
    if "sources" in patch and patch["sources"] is not None:
        if not isinstance(patch["sources"], list):
            raise ValueError("sources 必须是列表")
        out = []
        for s in patch["sources"][:MAX_SOURCES]:
            if not isinstance(s, dict) or not s.get("id") or not s.get("url"):
                continue
            p = urllib.parse.urlparse(str(s["url"]))
            if p.scheme not in ("http", "https") or not p.hostname:
                raise ValueError(f"信息源地址必须是 http/https URL: {s.get('url')}")
            out.append({"id": str(s["id"])[:60], "name": str(s.get("name") or s["id"])[:60],
                        "url": str(s["url"])[:300]})
        ids = [s["id"] for s in out]
        if len(ids) != len(set(ids)):
            raise ValueError("信息源 id 重复")
        cfg["sources"] = out
    # 只持久化「之前已保存的」+「本次 patch 的」键，默认层保持可随应用升级演进
    persist = {k: cfg[k] for k in (set(saved) | set(patch)) & set(cfg)}
    db.set_meta("campus_cfg", json.dumps(persist, ensure_ascii=False))
    return cfg


# ---------- 网络探测 ----------

def _probe(url: str) -> float | None:
    """探测可达性，返回延迟 ms；不可达返回 None。"""
    t0 = time.perf_counter()
    try:
        _fetch(url, timeout=PROBE_TIMEOUT, max_bytes=1024)
        return round((time.perf_counter() - t0) * 1000)
    except Exception:
        return None


def _public_ip_in_cidrs(cidrs: list[str]) -> bool | None:
    """查询本机公网出口 IP 并判断是否落在配置的校园网段内；无法判断返回 None。"""
    nets = []
    for c in cidrs:
        try:
            nets.append(ipaddress.ip_network(c, strict=False))
        except ValueError:
            continue
    if not nets:
        return None
    for echo in ("https://api.ipify.org", "http://cip.cc/ip", "https://ip.3322.net"):
        try:
            raw = _fetch(echo, timeout=PROBE_TIMEOUT, max_bytes=256).decode("utf-8", "replace")
            m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", raw)
            if not m:
                continue
            ip = ipaddress.ip_address(m.group(1))
            if any(ip in n for n in nets):
                return True
            return False  # 拿到了公网 IP 且不在校内网段 → 不在校内（按配置的网段）
        except Exception:
            continue
    return None


def detect(force: bool = False) -> dict:
    """网络状态检测（带 2 分钟缓存）。state 取值见 STATE_LABELS。"""
    with _detect_lock:
        if (not force and _detect_cache["result"]
                and time.time() - _detect_cache["ts"] < DETECT_CACHE_SECONDS):
            return _detect_cache["result"]

    cfg = get_cfg()
    campus_ms = None
    for host in cfg["campus_hosts"][:3]:
        campus_ms = _probe(f"http://{host}/")
        if campus_ms is not None:
            break
    external_ms = _probe(f"http://{cfg['external_host']}/")
    internal_ok = any(_probe(h if "//" in h else f"http://{h}/") is not None
                      for h in cfg["internal_hosts"][:3])

    state, detail = "offline", "校园站点与外网均不可达"
    if internal_ok:
        state = "campus"
        detail = "教务处等仅校内可达的站点连通，确认在校园网内"
    elif campus_ms is not None:
        ip_hit = _public_ip_in_cidrs(cfg["public_cidrs"]) if external_ms is not None else None
        if ip_hit or (ip_hit is None and external_ms is None):
            state = "campus" if ip_hit else "campus_likely"
            detail = ("公网出口 IP 命中示例大学网段（203.0.113.0.0/16）" if ip_hit
                      else "校内站点可达但外网不通：典型校园网未认证状态，校内信息源仍可同步")
        else:
            state = "public"
            detail = ("外网可达，但教务处等校内专用站点不可达——当前不在校园网环境"
                      "（如在校内请先完成认证；公网站点的信息源仍会同步）")
    elif external_ms is not None:
        state = "public"
        detail = "外网可达，校园站点不可达（可能不在校园网环境）"

    result = {"state": state, "label": STATE_LABELS[state], "detail": detail,
              "latency_campus_ms": campus_ms, "latency_external_ms": external_ms,
              "checked_at": time.time()}
    _detect_cache["ts"] = time.time()
    _detect_cache["result"] = result
    return result


# ---------- 信息源解析 ----------

def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gb18030", errors="replace")


def parse_listing(html: str, base_url: str) -> list[dict]:
    """从 CMS 列表页解析文章条目：标题 + 绝对链接 + 附近日期。

    匹配规则：href 指向本站文章页（Webplus `/YYYY/MMDD/cNNNaNNN/page.htm` 或 `/info/…`，
    过滤外链与广告）；标题按 嵌套标题容器（卡片式锚点）> title 属性 > 锚文本 顺序提取，
    去尾部日期；日期支持 `2026-09-07` / `2026.09.07` / `2026年9月7日`，统一归一化为
    YYYY-MM-DD，在「相邻文章锚点之间」的片段里取距锚点最近的。
    """
    matches = []
    for m in _ANCHOR_RE.finditer(html):
        if not _ARTICLE_HREF.search(m.group(1)):
            continue
        title = _clean_title(m.group(2), m.group(0))
        if len(title) >= 4:
            matches.append((m, title))
    base_host = urllib.parse.urlparse(base_url).hostname or ""
    items, seen = [], set()
    for i, (m, title) in enumerate(matches):
        url = urllib.parse.urljoin(base_url, m.group(1))
        if urllib.parse.urlparse(url).hostname != base_host:
            continue
        if url in seen:
            continue
        seen.add(url)
        seg_lo = matches[i - 1][0].end() if i else 0
        seg_hi = matches[i + 1][0].start() if i + 1 < len(matches) else len(html)
        seg_lo = max(seg_lo, m.start() - 200)
        seg = html[seg_lo: min(seg_hi, m.end() + 200)]
        a_pos = m.start() - seg_lo
        published, best = "", 10 ** 9
        for dm in _DATE_RE.finditer(seg):
            d = abs(dm.start() - a_pos)
            if d < best:
                best = d
                published = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
        items.append({"title": title[:200], "url": url, "published": published})
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


def fetch_source(source: dict) -> list[dict]:
    # 校园站点偶发瞬时 5xx/连接抖动，失败重试一次再判死
    try:
        return parse_listing(_decode(_fetch(source["url"])), source["url"])
    except OSError:
        time.sleep(1.5)
        return parse_listing(_decode(_fetch(source["url"])), source["url"])


# ---------- 同步 ----------

def _last_sync() -> dict | None:
    try:
        raw = db.get_meta("campus_last_sync")
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def sync() -> dict:
    """同步全部信息源；离线时跳过网络请求直接返回。"""
    state = detect()
    if state["state"] == "offline":
        result = {"added": 0, "network": "offline", "skipped": True, "sources": [],
                  "ts": time.time()}
        db.set_meta("campus_last_sync", json.dumps(result, ensure_ascii=False))
        return result

    cfg = get_cfg()
    added, per = 0, []
    for src in cfg["sources"]:
        try:
            items = fetch_source(src)
            n_new = 0
            for it in items:
                if db.campus_upsert(src["id"], it["title"], it["url"], it["published"]) == "added":
                    added += 1
                    n_new += 1
            per.append({"id": src["id"], "name": src["name"], "ok": True, "new": n_new,
                        "items": len(items),
                        **({} if items else {"warn": "未解析到条目（页面可能需要校园网/登录/为JS渲染）"})})
        except Exception as e:
            per.append({"id": src["id"], "name": src["name"], "ok": False,
                        "error": str(e)[:160]})
    db.campus_prune()
    result = {"added": added, "network": state["state"], "skipped": False,
              "sources": per, "ts": time.time()}
    db.set_meta("campus_last_sync", json.dumps(result, ensure_ascii=False))
    return result


def status() -> dict:
    cfg = get_cfg()
    return {
        "network": detect(),
        "last_sync": _last_sync(),
        "counts": db.campus_counts(),
        "total": db.campus_total(),
        "config": {k: cfg[k] for k in ("auto_sync", "interval_min", "sources",
                                       "campus_hosts", "internal_hosts", "public_cidrs")},
    }


def list_items(source: str = "", limit: int = 60, q: str = "") -> list[dict]:
    return db.campus_list(source, limit, q=q)


# ---------- 后台自动同步线程 ----------

_loop_started = False


def start_background_loop() -> None:
    """启动守护线程：每分钟检查一次，到期且非离线时自动同步。幂等。"""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def _run():
        time.sleep(20)  # 等服务与网络栈就绪，避免和启动期其他初始化抢带宽
        while True:
            try:
                cfg = get_cfg()
                last = _last_sync()
                last_ts = last["ts"] if last else 0
                if cfg["auto_sync"] and time.time() - last_ts >= cfg["interval_min"] * 60:
                    sync()
            except Exception:
                pass  # 后台同步失败不影响主服务，下一轮再试
            time.sleep(60)

    threading.Thread(target=_run, name="campus-sync", daemon=True).start()
