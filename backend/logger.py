"""
统一日志配置模块
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from .config import settings


class TSBotFormatter(logging.Formatter):
    """TSBot 统一日志格式化器"""
    
    def __init__(self):
        # 统一日志格式: [时间] [级别] [组件] 消息
        fmt = "[%(asctime)s] [%(levelname)s] [backend] %(message)s"
        super().__init__(fmt, datefmt="%Y-%m-%d %H:%M:%S")


def setup_logger(
    name: str = "tsbot-backend",
    level: str = "INFO",
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    设置统一的日志配置
    
    Args:
        name: logger 名称
        level: 日志级别 (DEBUG, INFO, WARN, ERROR)
        log_file: 日志文件路径，None 则只输出到控制台
    
    Returns:
        配置好的 logger
    """
    logger = logging.getLogger(name)
    
    # 避免重复配置
    if logger.handlers:
        return logger

    lvl = (level or "INFO").strip().upper()
    if lvl == "WARN":
        lvl = "WARNING"
    if not hasattr(logging, lvl):
        lvl = "INFO"
    logger.setLevel(getattr(logging, lvl))
    
    formatter = TSBotFormatter()
    
    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件输出
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# 全局 logger 实例
logger = setup_logger(
    level=getattr(settings, 'log_level', 'INFO'),
    log_file="logs/backend.log"
)
