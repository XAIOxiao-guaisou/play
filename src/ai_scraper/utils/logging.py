import sys
from loguru import logger

def setup_logger():
    """Configure loguru logger."""
    config = {
        "handlers": [
            {
                "sink": sys.stdout,
                "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                "level": "INFO",
            },
            {
                "sink": "logs/ai_scraper.log",
                "rotation": "10 MB",
                "retention": "1 week",
                "level": "DEBUG",
                "encoding": "utf-8",
            }
        ]
    }
    logger.configure(**config)
    return logger
