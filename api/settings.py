from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM providers
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""
    hf_token: str = ""
    tavily_api_key: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    use_sqlite: bool = False

    # Research tools
    searxng_url: str = "http://localhost:8080"
    jina_reader_url: str = "https://r.jina.ai"
    research_max_results: int = 5
    research_fetch_timeout: int = 5

    # Redis / workers
    redis_url: str = "redis://localhost:6379/0"
    worker_job_timeout: int = 600  # seconds; arq cancels jobs that exceed this

    # Storage
    aws_s3_bucket: str = ""
    aws_region: str = "us-east-1"
    use_local_fs: bool = True

    # Observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    max_iterations: int = 3
    artifact_ttl_days: int = 7


settings = Settings()
