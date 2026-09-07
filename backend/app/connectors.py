"""连接器（WorkBuddy: Connectors）。

- local_folder：本地文件夹导入（内置）
- mcp：MCP 标准协议客户端骨架，可挂载外部 MCP server
"""
import json
import os

import httpx

from . import db, rag
from .config import settings

# ---------- local_folder 连接器 ----------


def import_local_folder(space_id: str, folder: str) -> list[dict]:
    """把文件夹下所有 PDF/TXT/MD 导入空间并建立索引。"""
    results = []
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if not fn.lower().endswith((".pdf", ".txt", ".md", ".markdown")):
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

    通过 `studypilot mcp add <name> -- <command>` 方式配置后，
    list_tools / call_tool 可调用外部 MCP server 暴露的工具。
    """

    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = command
        self._proc = None
        self._req_id = 0

    def start(self):
        import subprocess
        if self._proc is None:
            self._proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, encoding="utf-8", shell=False)

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self.start()
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params or {}}
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
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

    def list_tools(self) -> list:
        result = self._rpc("tools/list")
        return result.get("tools", [])

    def call_tool(self, tool: str, arguments: dict) -> dict:
        return self._rpc("tools/call", {"name": tool, "arguments": arguments})


# 已注册的 MCP server（name -> command），可由 API 注册
_mcp_servers: dict[str, McpClient] = {}


def register_mcp(name: str, command: list[str]) -> None:
    _mcp_servers[name] = McpClient(name, command)


def list_connectors() -> dict:
    return {
        "builtin": [{"name": "local_folder", "description": "导入本地文件夹中的 PDF/TXT/MD 讲义"}],
        "mcp": [{"name": c.name, "command": c.command} for c in _mcp_servers.values()],
    }
