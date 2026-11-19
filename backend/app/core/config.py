from pydantic_settings import BaseSettings,SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
class Settings(BaseSettings):
    # DATABASE
    DB_HOST: str
    DB_PORT:int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    # Write the AI related stuff here:
    #AI_API_KEY:
    #AI_MODEL:

    # JWT Configuration
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()