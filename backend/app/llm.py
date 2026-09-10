"""LLM 网关：本地 / 云端双通道（OpenAI 兼容），按任务路由、失败回退。

- 本地通道：llama-server / Ollama / LM Studio（.env 配置）
- 云端通道：任意 OpenAI 兼容 API（.env 或运行时经 /api/llm/config 配置，持久化到 data/llm_config.json）
- 路由策略 routing：
    local  全部走本地（默认）
    auto   重任务（出题/判卷/分析/规划/抽取）走云端（若已配置），其余本地
    cloud  全部走云端，云端失败自动回退本地
- 连接复用：httpx.Client 连接池常驻；配置文件只允许位于 data 目录内，文件 I/O 全部走
  os.open + os.fdopen 描述符方式（不按路径打开，杜绝路径逃逸与 TOCTOU）。
"""
import json
import os
import threading
from typing import Iterator
from urllib.parse import urlparse

import httpx

from .config import settings

# 嵌入模型的离线开关延后到首次加载时决定（见 _configure_embed_offline）：
# 新环境模型还没缓存时不能强制离线，否则下载被禁、聊天/出题/索引全瘫痪

# 任务权重：auto 策略下这些任务优先走云端（重推理、长输出、结构化生成）
HEAVY_TASKS = {"quiz", "grade", "analyze", "plan", "extract"}

_cfg_lock = threading.RLock()  # 可重入：_get_client 持锁时会再经 _cloud_profile 触发 _ensure_runtime
_clients: dict[str, httpx.Client] = {}
_profiles: dict[str, dict] = {}      # profile -> {base_url, api_key, model}
_DATA_ROOT = os.path.realpath(settings.data_dir)  # 运行时配置文件只允许落在该目录内
_CONFIG_PATH = os.path.realpath(os.path.join(_DATA_ROOT, "llm_config.json"))
_CONFIG_TMP = os.path.realpath(os.path.join(_DATA_ROOT, "llm_config.json.tmp"))


def _guarded(path: str) -> str:
    """路径包含校验：必须位于 data 目录内，否则拒绝。"""
    p = os.path.realpath(path)
    if not p.startswith(_DATA_ROOT + os.sep):
        raise ValueError("LLM 配置文件路径异常")
    return p


def _read_config_file(path: str) -> str:
    fd = os.open(_guarded(path), os.O_RDONLY)
    with os.fdopen(fd, encoding="utf-8") as f:
        return f.read()


def _write_config_file(path: str, text: str) -> None:
    fd = os.open(_guarded(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def _load_runtime_config() -> dict:
    """云端配置：.env 为初始值，data/llm_config.json 的运行时修改优先。"""
    cfg = {"cloud_base_url": settings.cloud_base_url, "cloud_api_key": settings.cloud_api_key,
           "cloud_model": settings.cloud_model, "routing": settings.routing}
    try:
        cfg.update(json.loads(_read_config_file(_CONFIG_PATH)))
    except (OSError, ValueError):
        pass
    return cfg


_runtime: dict = {}
_runtime_loaded = False


def _ensure_runtime() -> dict:
    global _runtime_loaded
    with _cfg_lock:
        if not _runtime_loaded:
            _runtime.update(_load_runtime_config())
            _runtime_loaded = True
    return _runtime


def _save_runtime_config() -> None:
    os.makedirs(_DATA_ROOT, exist_ok=True)
    data = {k: _runtime.get(k, "") for k in
            ("cloud_base_url", "cloud_api_key", "cloud_model", "routing")}
    _write_config_file(_CONFIG_TMP, json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(_CONFIG_TMP, _CONFIG_PATH)


def update_runtime_config(cloud_base_url: str | None = None, cloud_api_key: str | None = None,
                          cloud_model: str | None = None, routing: str | None = None) -> None:
    _ensure_runtime()
    if routing is not None and routing not in ("local", "auto", "cloud"):
        # 先整体校验再动手，避免非法 routing 导致前序字段改了内存却没落盘
        raise ValueError("routing 必须是 local / auto / cloud")
    with _cfg_lock:
        if cloud_base_url is not None:
            _runtime["cloud_base_url"] = cloud_base_url.strip()
        if cloud_api_key is not None:
            _runtime["cloud_api_key"] = cloud_api_key.strip()
        if cloud_model is not None:
            _runtime["cloud_model"] = cloud_model.strip()
        if routing is not None:
            _runtime["routing"] = routing
        _save_runtime_config()
        for client in _clients.values():
            client.close()
        _clients.clear()


def get_status() -> dict:
    """供 /api/llm/config 展示（api_key 只回掩码）。"""
    rt = _ensure_runtime()
    cloud_ok = bool(rt.get("cloud_base_url") and rt.get("cloud_model"))
    key = rt.get("cloud_api_key", "")
    return {
        "routing": rt.get("routing", "local"),
        "local": {"base_url": settings.llm_base_url, "model": settings.llm_model},
        "cloud": {"base_url": rt.get("cloud_base_url", ""), "model": rt.get("cloud_model", ""),
                  "api_key_masked": (key[:4] + "****" + key[-4:]) if len(key) > 8 else ("已配置" if key else ""),
                  "configured": cloud_ok},
        "max_context_chars": settings.max_context_chars,
    }


def _local_profile() -> dict:
    return {"base_url": settings.llm_base_url, "api_key": settings.llm_api_key,
            "model": settings.llm_model}


def _cloud_profile() -> dict | None:
    rt = _ensure_runtime()
    if rt.get("cloud_base_url") and rt.get("cloud_model"):
        return {"base_url": rt["cloud_base_url"], "api_key": rt.get("cloud_api_key", ""),
                "model": rt["cloud_model"]}
    return None


def _routing() -> str:
    return _ensure_runtime().get("routing", "local")


def _pick_profile(task: str) -> str:
    """决定本次请求走哪个通道。"""
    routing = _routing()
    if routing == "cloud":
        return "cloud" if _cloud_profile() else "local"
    if routing == "auto" and task in HEAVY_TASKS:
        return "cloud" if _cloud_profile() else "local"
    return "local"


def _fallback_order(primary: str) -> list[str]:
    """通道尝试顺序。routing=local 是用户明确的"全部本地"承诺，
    失败也绝不能把请求（含对话内容）发往云端；cloud/auto 保持自动回退。"""
    if _routing() == "local":
        return ["local"]
    return [primary] + [p for p in ("local", "cloud") if p != primary]


def _get_client(profile: str) -> httpx.Client:
    with _cfg_lock:
        client = _clients.get(profile)
        if client is None:
            p = _local_profile() if profile == "local" else (_cloud_profile() or _local_profile())
            parsed = urlparse(p["base_url"])
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"LLM 端点协议必须是 http/https，当前: {p['base_url']}")
            client = httpx.Client(
                base_url=p["base_url"],
                headers={"Authorization": f"Bearer {p['api_key']}"},
                timeout=httpx.Timeout(900.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=2, keepalive_expiry=600.0),
                follow_redirects=False,
            )
            _clients[profile] = client
            _profiles[profile] = p
    return client


def _model_of(profile: str) -> str:
    p = _profiles.get(profile) or (_local_profile() if profile == "local" else (_cloud_profile() or _local_profile()))
    return p["model"]


def _strip_think(text: str) -> str:
    if "</think>" in text:  # 兼容 thinking 模型输出
        text = text.split("</think>", 1)[1]
    return text.strip()


def chat(messages: list[dict], temperature: float = 0.6, max_tokens: int = 2048,
         task: str = "chat") -> str:
    """带通道路由与回退的补全：首选通道失败时自动回退（routing=local 时只用本地）。"""
    order = _fallback_order(_pick_profile(task))
    last_err: Exception | None = None
    for profile in order:
        try:
            r = _get_client(profile).post("/chat/completions", json={
                "model": _model_of(profile), "messages": messages, "temperature": temperature,
                "max_tokens": max_tokens,
            })
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            if not text or not text.strip():
                raise ValueError("模型返回空内容")
            return _strip_think(text)
        except Exception as e:  # 网络/超时/云端报错 → 回退
            last_err = e
            if profile == order[-1]:
                break
    raise RuntimeError(f"LLM 调用失败（本地/云端均不可用）: {last_err}") from last_err


class _ThinkFilter:
    """跨 chunk 剥离 <think>…</think> 段（标签可能被切分在任意 delta 边界）。"""

    _OPEN, _CLOSE = "<think>", "</think>"

    def __init__(self):
        self.in_think = False
        self.tail = ""  # 末尾可能是被切断的半个标签，留到下个 chunk 再判

    def feed(self, delta: str) -> str:
        buf = self.tail + delta
        self.tail = ""
        out: list[str] = []
        while buf:
            tag = self._CLOSE if self.in_think else self._OPEN
            i = buf.find(tag)
            if i != -1:
                if not self.in_think:
                    out.append(buf[:i])
                buf = buf[i + len(tag):]
                self.in_think = not self.in_think
                continue
            # 没有完整标签：末尾若是标签前缀则留下次拼接，其余立即输出/丢弃
            keep = 0
            for k in range(min(len(buf), len(tag) - 1), 0, -1):
                if tag.startswith(buf[-k:]):
                    keep = k
                    break
            if keep:
                self.tail = buf[-keep:]
                buf = buf[:-keep]
            if not self.in_think and buf:
                out.append(buf)
            buf = ""
        return "".join(out)

    def flush(self) -> str:
        rest, self.tail = self.tail, ""
        return "" if self.in_think else rest


def chat_stream(messages: list[dict], temperature: float = 0.6, max_tokens: int = 2048,
                task: str = "chat") -> Iterator[str]:
    """流式补全：出首个可见内容前失败时回退备用通道；已开始输出后失败直接抛错，
    避免换通道重发导致回答前半截重复拼接。"""
    order = _fallback_order(_pick_profile(task))
    last_err: Exception | None = None
    for profile in order:
        filt = _ThinkFilter()
        emitted = False
        try:
            body = {"model": _model_of(profile), "messages": messages, "temperature": temperature,
                    "stream": True, "max_tokens": max_tokens}
            client = _get_client(profile)
            with client.stream("POST", "/chat/completions", json=body) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        delta = json.loads(payload)["choices"][0].get("delta", {}).get("content")
                    except (ValueError, KeyError, IndexError):
                        continue
                    if not delta:
                        continue
                    piece = filt.feed(delta)
                    if piece:
                        emitted = True
                        yield piece
                tail = filt.flush()
                if tail:
                    yield tail
                if not emitted and not tail:
                    raise ValueError("模型未返回可见内容（thinking 段未闭合或输出为空）")
                return
        except Exception as e:
            if emitted:
                raise  # 前半段已发给用户，重发只会拼接出重复内容
            last_err = e
            if profile == order[-1]:
                break
    raise RuntimeError(f"LLM 流式调用失败（本地/云端均不可用）: {last_err}") from last_err


_JSON_RETRY = "\n\n注意：刚才的输出不是合法 JSON。重新输出，只输出严格 JSON，不要任何解释、前后缀或代码块标记。"


def chat_json(messages: list[dict], temperature: float = 0.4, max_tokens: int = 2048,
              task: str = "analyze") -> object:
    """要求模型输出 JSON 并稳健解析：截取最外层 [..] / {..}，失败自动纠错重试一次。"""
    attempt_messages = list(messages)
    for attempt in range(2):
        raw = chat(attempt_messages, temperature=temperature if attempt == 0 else 0.2,
                   max_tokens=max_tokens, task=task)
        parsed = _extract_json(raw)
        if parsed is not None:
            return parsed
        attempt_messages = messages + [
            {"role": "assistant", "content": raw[:2000]},
            {"role": "user", "content": _JSON_RETRY},
        ]
    raise ValueError("模型未能输出合法 JSON")


def _extract_json(raw: str):
    # 优先整体解析，再按 {} -> [] 截取：对象里常嵌套数组（如 {"missed":[],"wrong":[]}），
    # 若先截 [] 会把内层数组误当解析结果返回，调用方拿到的类型就错了
    try:
        return json.loads(raw.strip())
    except ValueError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = raw.find(open_ch)
        end = raw.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except ValueError:
                continue
    return None


def _configure_embed_offline() -> None:
    """嵌入模型已在本地（目录或 HF 缓存）时才强制离线，避免每次加载联网校验拖慢；
    未缓存的新环境保持在线以便首次下载。"""
    model = settings.embed_model
    cached = os.path.isdir(model)
    if not cached:
        try:
            from huggingface_hub import snapshot_download
            try:
                snapshot_download(model, local_files_only=True)
                cached = True
            except Exception:
                cached = False
        except ImportError:
            cached = False
    if cached:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        # HF 库的 constants 在 import 时固化环境变量；若此刻库已被加载（如测试进程、
        # 懒加载晚于首轮 import），改环境变量无效，直接改常量兜底，
        # 否则断网/证书异常环境下每个配置文件都要吃 5 次退避重试（首聊卡 2-3 分钟）
        try:
            import huggingface_hub.constants as _hf_constants
            _hf_constants.HF_HUB_OFFLINE = True
        except Exception:
            pass


# 在本模块被 import 时（早于任何 sentence_transformers/transformers 导入）先判定缓存，
# 让 HF_HUB_OFFLINE 在 HF 库首次加载前生效
_configure_embed_offline()


def embed(texts: list[str]) -> list[list[float]]:
    return Embedder().encode(texts)


_emb_lock = threading.Lock()
_emb_model = None


class Embedder:
    def __init__(self):
        _configure_embed_offline()
        from sentence_transformers import SentenceTransformer
        global _emb_model
        with _emb_lock:
            if _emb_model is None:
                _emb_model = SentenceTransformer(settings.embed_model, device=settings.embed_device)
        self.model = _emb_model

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]
