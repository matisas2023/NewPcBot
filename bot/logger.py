import logging
from pathlib import Path


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("bot-actions")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    log_dir = Path("logs")
    log_file = log_dir / "actions.log"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Debian/systemd: якщо немає прав на файл, не падаємо —
        # пишемо у stdout/stderr, щоб бот продовжив працювати.
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.warning("Немає доступу до %s. Логування переключено у консоль.", log_file)

    return logger


_LOGGER = _build_logger()


def log_action(user_id: int, action: str, result: str = ""):
    """Логування дій користувача та системи."""
    if result:
        _LOGGER.info("User %s | %s | %s", user_id, action, result)
    else:
        _LOGGER.info("User %s | %s", user_id, action)
