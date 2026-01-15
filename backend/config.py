from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TSBOT_",
        env_file=str(Path(__file__).resolve().parent / ".env"),
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8009
    voice_grpc_addr: str = "127.0.0.1:50051"
    
    cookie_key: str = "dev-cookie-key"
    netease_api_base: str = "http://47.113.188.213:3000/"
    
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/backend.log"
    

    admin_token: str = ""


settings = Settings()
