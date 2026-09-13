"""B站视频课程导入：字幕时间线 → 时间戳转写文档 → 入库参与 RAG（P1，借鉴 DeepTutor 沉浸式视频学习）。

- 只做「有 CC 字幕（含 AI 字幕）的视频」：拉字幕 JSON → 转写为带 [mm:ss] 时间戳的文本文档，
  走现有解析/分块/向量化管线，答疑引用自带时间戳定位；
- 网络层域明白名单（仅 bilibili 官方 API 与 hdslb CDN），无字幕时如实报错，
  不做音频 ASR（本地算力跑不动长视频，v1 边界）；
- 转写/URL 解析/时间戳格式化均为纯函数，离线可测；网络函数失败给可读错误。
"""
import hashlib
import logging
import re

import httpx

from . import db, rag
from .routers.common import UPLOAD_ROOT

log = logging.getLogger("studypilot.video")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = 15.0
# 允许访问的域名：B站公开 API 与字幕 CDN。其余一律拒绝（不做成通用抓取器）
_API_HOST = "api.bilibili.com"
_SUB_HOST_SUFFIX = ".hdslb.com"
_GAP_SECONDS = 25.0     # 字幕间隔超过该值视为换话题，段落断开（chunk_text 按空行切）
_MAX_PARA_LINES = 10    # 单段落行数上限，保证 chunk 粒度均匀

_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")


def extract_bvid(url_or_id: str) -> str:
    """从 BV 号 / 视频页 URL / 短链文本中提取 BV 号；b23.tv 短链无法本地解析，明确报错。"""
    t = str(url_or_id or "").strip()
    if not t:
        raise ValueError("请填写 BV 号或视频链接")
    if "b23.tv" in t.lower():
        raise ValueError("暂不支持 b23.tv 短链，请在浏览器打开后复制地址栏的完整链接")
    m = _BV_RE.search(t)
    if not m:
        raise ValueError("未能从输入中识别 BV 号（形如 BV1xx411c7mD）")
    return m.group(0)


def _fmt_ts(seconds: float) -> str:
    """秒 → mm:ss（≥1 小时为 h:mm:ss）。负数按 0 处理（字幕数据偶尔有脏值）。"""
    s = max(0, int(round(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def transcript_from_subtitle(subtitle: dict, title: str, owner: str = "",
                             duration_sec: float | None = None) -> str:
    """bilibili CC 字幕 JSON → 带时间戳的转写文本（纯函数）。

    body 行 [{"from":1.2,"to":3.4,"content":"..."}]；
    段落切分：相邻行间隔 > _GAP_SECONDS 或段落满 _MAX_PARA_LINES 行——
    空行边界让 rag.chunk_text 优先在话题边界落刀。"""
    body = subtitle.get("body") if isinstance(subtitle, dict) else None
    if not isinstance(body, list) or not body:
        raise ValueError("字幕内容为空（body 缺失或无行）")
    head = f"【视频字幕】{title}"
    if owner:
        head += f"（UP：{owner}）"
    if duration_sec:
        head += f"，时长 {_fmt_ts(duration_sec)}"
    head += "\n以下为字幕时间线，答疑引用时可标注对应时间戳。"
    paras: list[list[str]] = []
    cur: list[str] = []
    prev_to = 0.0
    for row in body:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        start = float(row.get("from") or 0.0)
        if cur and (start - prev_to > _GAP_SECONDS or len(cur) >= _MAX_PARA_LINES):
            paras.append(cur)
            cur = []
        cur.append(f"[{_fmt_ts(start)}] {content}")
        prev_to = float(row.get("to") or start)
    if cur:
        paras.append(cur)
    if not paras:
        raise ValueError("字幕内容为空（无有效行）")
    return head + "\n\n" + "\n\n".join("\n".join(p) for p in paras)


def _check_host(url: str, suffix_ok: tuple[str, ...]) -> str:
    u = httpx.URL(url)
    host = u.host or ""
    if u.scheme not in ("http", "https"):
        raise ValueError(f"拒绝非 http(s) 地址: {url[:80]}")
    if host != _API_HOST and not any(host.endswith(s) for s in suffix_ok):
        raise ValueError(f"拒绝访问非 B 站域名: {host}")
    return url


def fetch_video_info(bvid: str) -> dict:
    """拉视频信息（公开接口）：title/owner/duration/cid/subtitles。失败给可读错误。"""
    api = _check_host(f"https://{_API_HOST}/x/web-interface/view?bvid={bvid}", ())
    try:
        r = httpx.get(api, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        raise ValueError(f"访问 B 站接口失败：{e}") from e
    except ValueError as e:
        raise ValueError("B 站接口返回了非 JSON 内容") from e
    if data.get("code") == -404:
        raise ValueError("视频不存在（BV 号可能有误）")
    if data.get("code") != 0:
        raise ValueError(f"B 站接口错误 code={data.get('code')}：{data.get('message', '')[:120]}")
    d = data.get("data") or {}
    subs = ((d.get("subtitle") or {}).get("subtitles")) or []
    return {"bvid": bvid, "title": str(d.get("title") or bvid),
            "owner": str((d.get("owner") or {}).get("name") or ""),
            "duration": float(d.get("duration") or 0),
            "subtitles": subs}


def fetch_subtitle_json(url: str) -> dict:
    """下载字幕 JSON（仅 hdslb CDN）。"""
    _check_host(url, (_SUB_HOST_SUFFIX,))
    try:
        r = httpx.get(url, headers={"User-Agent": _UA,
                                    "Referer": "https://www.bilibili.com/"}, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        raise ValueError(f"下载字幕失败：{e}") from e
    except ValueError as e:
        raise ValueError("字幕地址返回了非 JSON 内容") from e


_LAN_PRIORITY = ("zh-CN", "zh-Hans", "ai-zh", "zh")


def pick_subtitle(subs: list) -> dict:
    """按语言优先级选一条字幕：中文字幕优先，其次任意一条。"""
    if not isinstance(subs, list) or not subs:
        raise ValueError("该视频没有可用的 CC 字幕（UP 主未上传、AI 字幕不可用或需登录）")
    for lan in _LAN_PRIORITY:
        for s in subs:
            if isinstance(s, dict) and s.get("lan") == lan and s.get("subtitle_url"):
                return s
    for s in subs:
        if isinstance(s, dict) and s.get("subtitle_url"):
            return s
    raise ValueError("该视频没有可用的 CC 字幕（字幕条目均缺少下载地址）")


def ingest_video(space_id: str, url_or_id: str) -> dict:
    """导入入口：解析 → 拉信息 → 拉字幕 → 转写 → 落盘 → 建索引。"""
    bvid = extract_bvid(url_or_id)
    info = fetch_video_info(bvid)
    sub = pick_subtitle(info["subtitles"])
    sub_json = fetch_subtitle_json(sub["subtitle_url"])
    text = transcript_from_subtitle(sub_json, info["title"], info["owner"], info["duration"])
    # 磁盘名用随机 id（标题只做展示名），与上传端点同一套落盘边界
    path = str(UPLOAD_ROOT / f"{db.new_id()}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    display = f"【视频】{info['title']}.txt"
    did = db.add_document(space_id, display, path,
                          content_hash=hashlib.sha256(text.encode()).hexdigest())
    chunks = rag.index_document(space_id, did)
    return {"id": did, "bvid": bvid, "title": info["title"],
            "subtitle_lan": sub.get("lan") or "", "status": "ready", "chunks": chunks,
            "note": "字幕时间线已入库，答疑引用自带 [mm:ss] 时间戳"}
