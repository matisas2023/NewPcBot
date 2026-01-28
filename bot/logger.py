import logging
from pathlib import Path

# Створюємо папку logs якщо не існує
Path("logs").mkdir(exist_ok=True)

# Налаштування логування
logging.basicConfig(
    filename="logs/actions.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)

def log_action(user_id: int, action: str, result: str = ""):
    """
    Логування дій користувача та системи.
    """
    if result:
        logging.info(f"User {user_id} | {action} | {result}")
    else:
        logging.info(f"User {user_id} | {action}")
