import re
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
    netease_chat_quality: str = "AUTO"
    
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/backend.log"

    api_token: str = ""
    api_tokens: str = ""

    admin_token: str = ""
    initial_admin_password: str = ""
    initial_password_file: str = "./logs/initial-admin-password.txt"
    voice_config_file: str = "./logs/voice-service.json"
    web_app_name: str = "Yumi TSBot"
    web_app_icon: str = ""
    web_log_level: str = "INFO"
    voice_description_title: str = "Yumi TSBot"
    voice_description_intro: str = "TeamSpeak 音乐机器人\\n支持网易云 / QQ 音乐 / B站"
    bilibili_max_duration_minutes: int = 180
    bilibili_audio_cache_ttl_hours: int = 72
    bilibili_audio_cache_max_mb: int = 2048
    bilibili_audio_partial_ttl_minutes: int = 60

    def get_api_tokens(self) -> list[str]:
        tokens: list[str] = []
        for raw in (self.api_token, self.api_tokens):
            for part in re.split(r"[\s,]+", raw or ""):
                token = part.strip()
                if token and token not in tokens:
                    tokens.append(token)
        return tokens


settings = Settings()
