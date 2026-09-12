from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI 兼容端点：llama-server / Ollama / LM Studio / 云端 API 均可
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_api_key: str = "none"
    llm_model: str = "qwen3-instruct-30b"
    # 单次 LLM 调用的读超时（秒）：覆盖流式相邻 chunk 与非流式整段响应的等待。
    # 900s 会让假死的服务把请求挂满 15 分钟；流式下它只约束两次到达之间的间隔，不影响长回答
    llm_timeout_s: float = 300.0

    # Embedding：默认轻量中文模型，显存充裕可换 BAAI/bge-m3
    embed_model: str = "BAAI/bge-small-zh-v1.5"
    embed_device: str = "cuda"  # 无 CUDA 时运行时自动回退 cpu；也可强制 LLM_EMBED_DEVICE=cpu

    db_path: str = "studypilot.db"
    upload_dir: str = "uploads"
    data_dir: str = "data"

    # 云端通道（可选）：配置后可按路由策略把重任务交给云端模型
    cloud_base_url: str = ""      # LLM_CLOUD_BASE_URL，OpenAI 兼容端点
    cloud_api_key: str = ""       # LLM_CLOUD_API_KEY
    cloud_model: str = ""         # LLM_CLOUD_MODEL
    routing: str = "local"        # LLM_ROUTING: local / auto / cloud
                                  #   local=全本地；auto=重任务(出题/判卷/分析/规划)走云端，其余本地；
                                  #   cloud=全云端（失败自动回退本地）
    max_context_chars: int = 12000  # 单次请求的 prompt 字符预算，防止超上下文被截断导致降智

    # RAG 检索：向量 + BM25 词法双通道 RRF 融合（RAG_HYBRID=0 可退回纯向量）
    hybrid_search: bool = True
    # 可选 cross-encoder 精排模型（RERANK_MODEL，如 BAAI/bge-reranker-v2-m3）：
    # 留空关闭；配置后答疑/出题检索末段重排，模型首次使用时自动下载
    rerank_model: str = ""


settings = Settings()
