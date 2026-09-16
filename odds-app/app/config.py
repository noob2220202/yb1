from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./oddsapp.db"

    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"

    default_total_stake: float = 30000.0

    ingest_interval_minutes: int = 15
    ingest_urgent_interval_minutes: int = 5
    ingest_urgent_window_hours: int = 3
    ingest_lookahead_hours: int = 72

    enable_scheduler: bool = True


settings = Settings()
