from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI 兼容端点：llama-server / Ollama / LM Studio / 云端 API 均可
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_api_key: str = "none"
    llm_model: str = "qwen3-instruct-30b"

    # Embedding：默认轻量中文模型，显存充裕可换 BAAI/bge-m3
    embed_model: str = "BAAI/bge-small-zh-v1.5"
    embed_device: str = "cuda"  # 无 GPU 环境改为 cpu

    db_path: str = "studypilot.db"
    upload_dir: str = "uploads"
    data_dir: str = "data"

    chat_base_url: str = ""  # 前端跨机访问时后端对外地址，留空则同源


settings = Settings()
