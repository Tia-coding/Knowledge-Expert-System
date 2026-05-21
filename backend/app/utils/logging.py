import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.config.settings import get_settings


def configure_logging() -> None:
    settings = get_settings()
    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        Path(settings.log_dir) / "app.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )