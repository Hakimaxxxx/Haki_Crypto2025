from pydantic import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Crypto Analytics API"
    environment: str = "dev"
    mongo_uri: str | None = None
    cloud_db_name: str | None = None

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
