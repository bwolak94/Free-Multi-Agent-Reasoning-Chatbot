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

    # Storage — Cloudflare R2 (S3-compatible)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "chatbot-artifacts"
    r2_endpoint: str = ""  # https://<account_id>.r2.cloudflarestorage.com
    use_local_fs: bool = True
    artifacts_local_path: str = "artifacts"

    # Image generation
    pollinations_url: str = "https://image.pollinations.ai"
    hf_inference_model: str = "black-forest-labs/FLUX.1-schnell"
    hf_inference_timeout: int = 120
    image_default_width: int = 1280
    image_default_height: int = 720

    # Video generation
    hf_video_space: str = "Wan-AI/Wan2.1-T2V-14B"
    hf_video_api_name: str = "/generate"

    # Observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # Auth — JWT signing key (generate with: openssl rand -hex 32)
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_hours: int = 8

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    max_iterations: int = 3
    artifact_ttl_days: int = 7


settings = Settings()
