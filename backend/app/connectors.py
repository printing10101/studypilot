"""连接器（WorkBuddy: Connectors）。

- local_folder：本地文件夹导入（内置）
- mcp：MCP 标准协议客户端骨架，可挂载外部 MCP server
"""
import atexit
import json
import os
import queue
import threading
import time

import httpx

from . import db, ingest, rag
from .config import settings

# ---------- local_folder 连接器 ----------


def import_local_folder(space_id: str, folder: str) -> list[dict]:
    """把文件夹下所有 PDF/TXT/MD 导入空间并建立索引（同一文件不重复导入）。"""
    results = []
    seen_paths = {os.path.abspath(r["path"]) for r in db.rows_to_dicts(
        db.get_conn().execute(
            "SELECT path FROM documents WHERE space_id=?", (space_id,)).fetchall()) if r["path"]}
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if not fn.lower().endswith(ingest.DOC_EXTS + ingest.IMAGE_EXTS):
                continue
            path = os.path.join(root, fn)
            if os.path.abspath(path) in seen_paths:
                continue
            did = db.add_document(space_id, fn, path)
            try:
                n = rag.index_document(space_id, did)
                seen_paths.add(os.path.abspath(path))
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
        self._lines: queue.Queue = queue.Queue()
        # 响应按 id 匹配但从同一条共享队列逐行消费：并发 RPC 会把对方响应当
        # "不匹配"丢掉导致其超时，整个请求-响应周期必须串行（RLock 供 ensure_init 嵌套）
        self._lock = threading.RLock()

    def start(self):
        import subprocess
        if self._proc is None:
            self._proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, encoding="utf-8", shell=False)
            # 独立读线程把 stdout 泵入队列：readline() 直接读会无限阻塞，
            # server 挂起时整个聊天请求都会被卡死
            threading.Thread(target=self._pump, daemon=True, name=f"mcp-{self.name}").start()

    def stop(self) -> None:
        """终止子进程并回收资源：terminate 不够时升级 kill，防止 npx 等
        wrapper 场景留下孤儿进程。注册重名覆盖/移除/应用退出时都必须调用。"""
        proc, self._proc = self._proc, None
        self._inited = False
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _pump(self) -> None:
        try:
            assert self._proc and self._proc.stdout
            for line in self._proc.stdout:
                self._lines.put(line)
        except Exception:
            pass
        self._lines.put("")  # EOF 哨兵

    def _send(self, payload: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

    def _rpc(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        with self._lock:
            self.start()
            assert self._proc and self._proc.stdout
            self._req_id += 1
            req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params or {}}
            self._send(req)
            while True:
                try:
                    line = self._lines.get(timeout=timeout)
                except queue.Empty:
                    raise RuntimeError(f"MCP server {self.name} 响应超时（>{int(timeout)}s）")
                if not line:
                    # server 进程已退出：复位状态，下次调用自动重启，而不是永久报错到重启应用
                    self._proc = None
                    self._inited = False
                    raise RuntimeError(f"MCP server {self.name} 无响应（进程已退出，将自动重启）")
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue  # 非 JSON 行（server 日志等）跳过
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
        with self._lock:
            if not self._inited:
                self.initialize()
                # initialized 通知无 id、无响应，直接发送即可
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self._inited = True

    def list_tools(self, timeout: float = 15.0) -> list:
        self.ensure_init()
        return self._rpc("tools/list", timeout=timeout).get("tools", [])

    def call_tool(self, tool: str, arguments: dict, timeout: float = 120.0) -> dict:
        self.ensure_init()
        return self._rpc("tools/call", {"name": tool, "arguments": arguments}, timeout=timeout)


# 已注册的 MCP server（name -> command），注册持久化在 meta 表，重启后自动恢复
_mcp_servers: dict[str, McpClient] = {}
_MCP_META_KEY = "mcp_servers"


def load_persisted() -> None:
    try:
        reg = json.loads(db.get_meta(_MCP_META_KEY) or "{}")
    except ValueError:
        reg = {}
    for name, command in reg.items():
        # 与 register_mcp 同一校验：跳过 meta 表里的空/畸形条目
        if (name not in _mcp_servers and isinstance(command, list)
                and name.strip() and command
                and all(isinstance(a, str) and a.strip() for a in command)):
            _mcp_servers[name] = McpClient(name, command)


def register_mcp(name: str, command: list[str]) -> None:
    # 入参校验：注册的 command 会被本机 subprocess 执行，拒绝空值/超长/空参数
    name = (name or "").strip()[:60]
    command = [str(a).strip()[:512] for a in (command or []) if str(a).strip()]
    if not name:
        raise ValueError("server 名称不能为空")
    if not command:
        raise ValueError("启动命令不能为空")
    if len(command) > 32:
        raise ValueError("启动命令参数过多（上限 32 个）")
    # 先停掉同名旧实例再覆盖：直接覆盖会泄漏旧 MCP 子进程
    old = _mcp_servers.get(name)
    if old is not None:
        try:
            old.stop()
        except Exception:
            pass
    _mcp_servers[name] = McpClient(name, command)
    _invalidate_tools_cache()
    db.set_meta(_MCP_META_KEY, json.dumps(
        {n: c.command for n, c in _mcp_servers.items()}, ensure_ascii=False))


def remove_mcp(name: str) -> bool:
    if name not in _mcp_servers:
        return False
    client = _mcp_servers.pop(name)
    try:
        client.stop()  # terminate+wait+kill 兜底，防孤儿进程
    except Exception:
        pass
    _invalidate_tools_cache()
    db.set_meta(_MCP_META_KEY, json.dumps(
        {n: c.command for n, c in _mcp_servers.items()}, ensure_ascii=False))
    return True


@atexit.register
def _shutdown_mcp_servers() -> None:
    """应用退出时回收所有 MCP 子进程，不留孤儿。"""
    for client in list(_mcp_servers.values()):
        try:
            client.stop()
        except Exception:
            pass


_TOOLS_TTL = 300.0  # 工具清单缓存 5 分钟，避免每条聊天消息都同步拉一遍 list_tools
_tools_cache: list[dict] | None = None
_tools_cached_at = 0.0
_tools_lock = threading.Lock()


def _invalidate_tools_cache() -> None:
    global _tools_cache
    with _tools_lock:
        _tools_cache = None


def all_tools() -> list[dict]:
    """汇总所有已注册 server 的工具清单：[{server, name, description}]。

    带缓存（TTL 5 分钟），单个 server 失败/超时只影响它自己的工具。
    锁只护缓存读写：list_tools 是最长 15s 的阻塞 RPC，放在锁内会让
    并发聊天请求全部排队。"""
    global _tools_cache, _tools_cached_at
    with _tools_lock:
        if _tools_cache is not None and time.time() - _tools_cached_at < _TOOLS_TTL:
            return _tools_cache
    # 快照后再遍历：register/remove 并发改字典时不会 RuntimeError
    tools = []
    for client in list(_mcp_servers.values()):
        try:
            for t in client.list_tools():
                tools.append({"server": client.name, "name": t.get("name", ""),
                              "description": (t.get("description") or "")[:200]})
        except Exception:
            continue
    with _tools_lock:
        _tools_cache = tools
        _tools_cached_at = time.time()
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
