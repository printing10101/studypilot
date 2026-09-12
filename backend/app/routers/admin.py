"""系统与运维：健康检查、专家团目录、LLM 通道配置/实测/统计、MCP 连接器。"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import connectors, experts, llm, llm_stats
from ..config import settings

router = APIRouter()


class LlmConfigIn(BaseModel):
    routing: str | None = None
    cloud_base_url: str | None = None
    cloud_api_key: str | None = None
    cloud_model: str | None = None
    local_base_url: str | None = None
    local_api_key: str | None = None
    local_model: str | None = None


class LlmTestIn(BaseModel):
    """「测试连通」可携带表单里正在编辑的值：未传字段回退到已保存配置。"""
    local_base_url: str = ""
    local_api_key: str = ""
    local_model: str = ""
    cloud_base_url: str = ""
    cloud_api_key: str = ""
    cloud_model: str = ""


class McpIn(BaseModel):
    name: str
    command: list[str]


@router.get("/api/health")
def health():
    # 健康检查用独立短超时客户端：复用 900s 推理客户端时，本地服务假死
    # （接受连接不响应）会把每次轮询都挂住最长 15 分钟
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
            models = client.get(f"{settings.llm_base_url.rstrip('/')}/models").json()
        llm_ok = True
    except Exception as e:
        models = {"error": str(e)[:200]}
        llm_ok = False
    return {"status": "ok", "llm": llm_ok, "model": settings.llm_model, "models": models}


@router.get("/api/experts")
def api_experts():
    return [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "system"}} for k, v in experts.EXPERTS.items()]


# ---------- LLM 通道配置（本地 / 云端） ----------

@router.get("/api/llm/config")
def api_llm_config():
    return llm.get_status()


@router.put("/api/llm/config")
def api_llm_update(body: LlmConfigIn):
    try:
        llm.update_runtime_config(routing=body.routing, cloud_base_url=body.cloud_base_url,
                                  cloud_api_key=body.cloud_api_key, cloud_model=body.cloud_model,
                                  local_base_url=body.local_base_url, local_api_key=body.local_api_key,
                                  local_model=body.local_model)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return llm.get_status()


@router.post("/api/llm/test")
def api_llm_test(body: LlmTestIn | None = None):
    """实测两个通道：各发一条极短补全，报告连通性与延迟。
    支持携带表单当前值直接测——否则「新填端点 → 立即测试」测的还是已保存配置，容易误报。"""
    overrides = body or LlmTestIn()
    if overrides.local_base_url or overrides.local_model:
        probe_local = llm.probe_profile(base_url=overrides.local_base_url or "",
                                        api_key=overrides.local_api_key or "",
                                        model=overrides.local_model or "", profile="local")
    else:
        probe_local = llm.probe_latency("local")
    if overrides.cloud_base_url or overrides.cloud_model:
        probe_cloud = llm.probe_profile(base_url=overrides.cloud_base_url or "",
                                        api_key=overrides.cloud_api_key or "",
                                        model=overrides.cloud_model or "", profile="cloud")
    else:
        probe_cloud = llm.probe_latency("cloud") if llm._cloud_profile() \
            else {"ok": False, "error": "未配置"}
    return {"local": probe_local, "cloud": probe_cloud}


@router.get("/api/llm/stats")
def api_llm_stats(hours: int = 24):
    """最近 N 小时的 LLM 调用统计：按通道/任务的延迟分布与成功率。"""
    return {
        "summary": llm_stats.summary(hours=hours),
        "health": llm_stats.channel_health(),
        "task_routing": {k: v["priority"] for k, v in llm.TASK_ROUTING.items()},
    }


@router.get("/api/llm/usage")
def api_llm_usage(days: int = 30):
    """用量仪表盘：按天/通道/任务/模型聚合 Token 与调用次数。"""
    return llm_stats.usage_dashboard(days=max(1, min(days, 90)))


@router.post("/api/llm/stats/clear")
def api_llm_stats_clear():
    llm_stats.clear_history()
    return {"ok": True}


# ---------- 连接器（MCP） ----------

@router.get("/api/connectors")
def api_connectors():
    return connectors.list_connectors()


@router.post("/api/connectors/mcp")
def api_register_mcp(body: McpIn):
    try:
        connectors.register_mcp(body.name, body.command)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.delete("/api/connectors/mcp/{name}")
def api_remove_mcp(name: str):
    if not connectors.remove_mcp(name):
        raise HTTPException(404, "未注册的 MCP server")
    return {"ok": True}
