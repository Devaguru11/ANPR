from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_name: str = "bert-base-uncased"
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
