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
    # "gemini-2.5-flash"는 신규 키 발급 계정에서 404로 막힌 게 실측 확인됨(구글이 신규 사용자에게
    # 구버전 모델 접근을 막음) - latest 별칭을 써서 이런 모델 세대교체에 자동으로 따라가게 함
    gemini_model: str = "gemini-flash-latest"
    gemini_image_model: str = "gemini-3.1-flash-image"

    anthropic_api_key: str = ""
    # `claude setup-token`으로 발급한 구독 인증 토큰. 있으면 Claude Code CLI가 구독 사용량으로
    # 동작하고(비용 0), 없거나 한도를 넘으면 anthropic_api_key로 폴백한다.
    claude_code_oauth_token: str = ""
    # CLI(구독)에서 쓸 모델. 마케팅 카피·연출·검수처럼 뉘앙스가 성과를 가르는 일은 상위 모델을
    # 쓰고(구독이라 추가 비용 없음), 단순 라우팅은 가벼운 모델로 구독 사용량을 아낀다.
    claude_cli_model: str = "claude-opus-5"
    claude_cli_light_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    google_gemini_api_key: str = ""

    google_calendar_mcp_enabled: bool = False

    github_token: str = ""
    github_repo: str = "charislab-ai/Operation"

    @property
    def allowed_email_list(self) -> list[str]:
        return [e.strip() for e in self.allowed_emails.split(",") if e.strip()]


settings = Settings()
