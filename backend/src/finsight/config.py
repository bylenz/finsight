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


settings = Settings()
