"""连接器（WorkBuddy: Connectors）。

- local_folder：本地文件夹导入（内置）
- mcp：MCP 标准协议客户端骨架，可挂载外部 MCP server
"""
import json
import os

import httpx

from . import db, ingest, rag
from .config import settings

# ---------- local_folder 连接器 ----------


def import_local_folder(space_id: str, folder: str) -> list[dict]:
    """把文件夹下所有 PDF/TXT/MD 导入空间并建立索引。"""
    results = []
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if not fn.lower().endswith(ingest.DOC_EXTS + ingest.IMAGE_EXTS):
                continue
            path = os.path.join(root, fn)
            did = db.add_document(space_id, fn, path)
            try:
                n = rag.index_document(space_id, did)
                results.append({"filename": fn, "status": "ready", "chunks": n})
            except Exception as e:
                results.append({"filename": fn, "status": "error", "error": str(e)[:200]})
    return results


# ---------- MCP 客户端骨架 ----------

class McpClient:
    """最小 MCP 客户端（stdio 传输），用于挂载外部工具 server。

    通过 `POST /api/connectors/mcp` 注册后，list_tools / call_tool 可调用
    外部 MCP server 暴露的工具；答疑专家会在需要时调用（注册持久化到 meta 表）。
    """

    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = command
        self._proc = None
        self._req_id = 0
        self._inited = False

    def start(self):
        import subprocess
        if self._proc is None:
            self._proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, encoding="utf-8", shell=False)

    def _send(self, payload: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self.start()
        assert self._proc and self._proc.stdout
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params or {}}
        self._send(req)
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP server {self.name} 无响应")
            msg = json.loads(line)
            if msg.get("id") == self._req_id:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg["result"]

    def initialize(self) -> dict:
        return self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "studypilot", "version": "0.1.0"},
        })

    def ensure_init(self) -> None:
        if not self._inited:
            self.initialize()
            # initialized 通知无 id、无响应，直接发送即可
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._inited = True

    def list_tools(self) -> list:
        self.ensure_init()
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, tool: str, arguments: dict) -> dict:
        self.ensure_init()
        return self._rpc("tools/call", {"name": tool, "arguments": arguments})


# 已注册的 MCP server（name -> command），注册持久化在 meta 表，重启后自动恢复
_mcp_servers: dict[str, McpClient] = {}
_MCP_META_KEY = "mcp_servers"


def load_persisted() -> None:
    try:
        reg = json.loads(db.get_meta(_MCP_META_KEY) or "{}")
    except ValueError:
        reg = {}
    for name, command in reg.items():
        if name not in _mcp_servers and isinstance(command, list):
            _mcp_servers[name] = McpClient(name, command)


def register_mcp(name: str, command: list[str]) -> None:
    _mcp_servers[name] = McpClient(name, command)
    db.set_meta(_MCP_META_KEY, json.dumps(
        {n: c.command for n, c in _mcp_servers.items()}, ensure_ascii=False))


def remove_mcp(name: str) -> bool:
    if name not in _mcp_servers:
        return False
    client = _mcp_servers.pop(name)
    try:
        if client._proc:
            client._proc.terminate()
    except Exception:
        pass
    db.set_meta(_MCP_META_KEY, json.dumps(
        {n: c.command for n, c in _mcp_servers.items()}, ensure_ascii=False))
    return True


def all_tools() -> list[dict]:
    """汇总所有已注册 server 的工具清单：[{server, name, description}]，单个失败不影响整体。"""
    tools = []
    for client in _mcp_servers.values():
        try:
            for t in client.list_tools():
                tools.append({"server": client.name, "name": t.get("name", ""),
                              "description": (t.get("description") or "")[:200]})
        except Exception:
            continue
    return tools


def call_mcp_tool(server: str, tool: str, arguments: dict) -> str:
    client = _mcp_servers.get(server)
    if not client:
        raise ValueError(f"MCP server {server} 未注册")
    result = client.call_tool(tool, arguments)
    texts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)]
    return "\n".join(t for t in texts if t) or str(result)[:1000]


def list_connectors() -> dict:
    return {
        "builtin": [{"name": "local_folder", "description": "导入本地文件夹中的 PDF/TXT/MD 讲义"}],
        "mcp": [{"name": c.name, "command": c.command} for c in _mcp_servers.values()],
    }
