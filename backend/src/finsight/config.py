from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://finsight:finsight@db:5432/finsight")
    jwt_secret: str = Field(default="change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expires_hours: int = Field(default=24)

    anthropic_api_key: str = Field(default="")
    # Empty = official Anthropic API. Set to "https://api.z.ai/api/anthropic" for Z.ai's
    # Anthropic-compatible GLM endpoint, or any other Anthropic-protocol provider.
    anthropic_base_url: str = Field(default="")
    # Model id passed to messages.create(). Default targets Anthropic Claude Hauku;
    # for Z.ai use "glm-4.5-air" (haiku-class) or "glm-4.6" (sonnet-class).
    llm_model: str = Field(default="claude-haiku-4-5-20251001")

    base_currency: str = Field(default="PEN")
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Rate limiting (SlowAPI) ---
    # Set to False in test environments to prevent CI flake.
    # Dedicated rate-limit tests override this to True.
    rate_limit_enabled: bool = Field(default=False)
    # Production: "5/minute". Tests: permissive default (limiter disabled anyway).
    rate_limit_login: str = Field(default="5/minute")
    # Production: "60/minute". Tests: permissive default.
    rate_limit_expense_create: str = Field(default="60/minute")

    # --- LLM categorizer guard ---
    # When False (default), the LLM is skipped and "Other" is returned directly.
    llm_categorizer_enabled: bool = Field(default=True)
    # Number of consecutive LLM failures before the circuit breaker opens.
    llm_circuit_breaker_threshold: int = Field(default=5)


settings = Settings()
