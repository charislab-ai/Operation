from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_db_url: str = ""

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    allowed_emails: str = ""

    telegram_bot_token: str = ""
    telegram_ceo_chat_id: str = ""
    telegram_webhook_secret: str = ""

    session_secret: str = ""
    session_ttl_hours: int = 12

    social_adapter: str = "mock"

    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_page_access_token: str = ""
    meta_page_id: str = ""
    meta_instagram_business_account_id: str = ""

    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""

    llm_provider: str = "claude"
    anthropic_model: str = "claude-sonnet-5"
    image_provider: str = "mock"
    image_quality: str = "medium"  # gpt-image-1: low|medium|high - high는 장당 비용이 커서 기본은 medium
    video_provider: str = "sora"
    vision_provider: str = "gemini"
    embedding_provider: str = "openai"
    gemini_model: str = "gemini-2.5-flash"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_gemini_api_key: str = ""

    google_calendar_mcp_enabled: bool = False

    @property
    def allowed_email_list(self) -> list[str]:
        return [e.strip() for e in self.allowed_emails.split(",") if e.strip()]


settings = Settings()
