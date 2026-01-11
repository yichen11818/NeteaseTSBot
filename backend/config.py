from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TSBOT_",
        env_file=str(Path(__file__).resolve().parent / ".env"),
        extra="ignore",
    )

    jwt_secret: str = "dev-change-me"
    cookie_key: str = "dev-cookie-key"

    netease_api_base: str = "http://127.0.0.1:3000"
    voice_grpc_addr: str = "127.0.0.1:50051"

    admin_username: str = "admin"
    admin_password: str = "admin"


settings = Settings()
