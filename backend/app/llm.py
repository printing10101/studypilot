"""LLM 网关：OpenAI 兼容 chat/completions；Embedding：sentence-transformers。

端点由配置指定且仅允许 http/https 协议（本地部署场景为 127.0.0.1 的 llama-server，
同时兼容 Ollama / LM Studio / 云端 API）。
"""
import json
import os
import threading
from typing import Iterator
from urllib.parse import urlparse

import httpx

from .config import settings

# 模型已缓存本地后无需联网校验，避免网络问题拖慢嵌入
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _get_client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            parsed = urlparse(settings.llm_base_url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"LLM_BASE_URL 协议必须是 http/https，当前: {settings.llm_base_url}")
            _client = httpx.Client(
                base_url=settings.llm_base_url,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                timeout=httpx.Timeout(900.0, connect=10.0),
                follow_redirects=False,
            )
    return _client


def chat(messages: list[dict], temperature: float = 0.6, max_tokens: int = 2048) -> str:
    r = _get_client().post("/chat/completions", json={
        "model": settings.llm_model, "messages": messages, "temperature": temperature,
        "max_tokens": max_tokens,
    })
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    if "</think>" in text:  # 兼容 thinking 模型输出
        text = text.split("</think>", 1)[1]
    return text.strip()


def chat_stream(messages: list[dict], temperature: float = 0.6, max_tokens: int = 2048) -> Iterator[str]:
    body = {"model": settings.llm_model, "messages": messages, "temperature": temperature,
            "stream": True, "max_tokens": max_tokens}
    r = _get_client().build_request("POST", "/chat/completions", json=body)
    in_think = False
    with _get_client().stream("POST", "/chat/completions", json=body) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            delta = json.loads(payload)["choices"][0].get("delta", {}).get("content")
            if not delta:
                continue
            if "<think>" in delta:
                in_think = True
            if "</think>" in delta:
                in_think = False
                continue
            if not in_think:
                yield delta
    del r


_emb_lock = threading.Lock()
_emb_model = None


class Embedder:
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        global _emb_model
        with _emb_lock:
            if _emb_model is None:
                _emb_model = SentenceTransformer(settings.embed_model, device=settings.embed_device)
        self.model = _emb_model

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]


def embed(texts: list[str]) -> list[list[float]]:
    return Embedder().encode(texts)
