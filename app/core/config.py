from __future__ import annotations

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = Field(default="AI Workspace Backend", alias="APP_NAME")
    env: str = Field(default="dev", alias="ENV")
    debug: bool = Field(default=False, alias="DEBUG")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    jwt_secret: str = Field(default="CHANGE_ME", alias="JWT_SECRET")
    jwt_alg: str = Field(default="HS256", alias="JWT_ALG")
    access_token_minutes: int = Field(default=60, alias="ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(default=30, alias="REFRESH_TOKEN_DAYS")

    # Works for local docker-compose (mongo service named "mongo").
    # Atlas users override via .env
    mongo_uri: str = Field(default="mongodb://mongo:27017", alias="MONGO_URI")
    mongo_db: str = Field(default="ai_workspace", alias="MONGO_DB")

    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_timeout_sec: int = Field(default=60, alias="OPENAI_TIMEOUT_SEC")

    openai_embed_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBED_MODEL")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_chunk_size: int = Field(default=1200, alias="RAG_CHUNK_SIZE")
    rag_chunk_overlap: int = Field(default=200, alias="RAG_CHUNK_OVERLAP")

    storage_dir: str = Field(default="/app/storage", alias="STORAGE_DIR")

    free_chat_per_day: int = Field(default=50, alias="FREE_CHAT_PER_DAY")
    free_pdf_pages_per_day: int = Field(default=50, alias="FREE_PDF_PAGES_PER_DAY")
    free_image_per_day: int = Field(default=5, alias="FREE_IMAGE_PER_DAY")

    pro_chat_per_day: int = Field(default=500, alias="PRO_CHAT_PER_DAY")
    pro_pdf_pages_per_day: int = Field(default=1000, alias="PRO_PDF_PAGES_PER_DAY")
    pro_image_per_day: int = Field(default=100, alias="PRO_IMAGE_PER_DAY")

    openai_image_model: str = Field(default="gpt-image-1", alias="OPENAI_IMAGE_MODEL")
    openai_image_size: str = Field(default="1024x1024", alias="OPENAI_IMAGE_SIZE")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")

    mcp_base_url: str = Field(default="http://mcp:9000", alias="MCP_BASE_URL")
    agent_max_hops: int = Field(default=3, alias="AGENT_MAX_HOPS")

    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_pro_monthly: str = Field(default="", alias="STRIPE_PRICE_PRO_MONTHLY")
    stripe_success_url: str = Field(default="http://localhost:3000/billing/success", alias="STRIPE_SUCCESS_URL")
    stripe_cancel_url: str = Field(default="http://localhost:3000/billing/cancel", alias="STRIPE_CANCEL_URL")
    stripe_portal_return_url: str = Field(default="http://localhost:3000/settings/billing", alias="STRIPE_PORTAL_RETURN_URL")

    def cors_origin_list(self) -> List[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()