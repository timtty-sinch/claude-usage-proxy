from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLAUDE_PROXY_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8082
    upstream_url: str = "https://api.anthropic.com"
    db_path: str = "claude_proxy.db"


settings = Settings()
