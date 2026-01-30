# bot/security/allowed_users.py

from bot.config import ALLOWED_USERS

def is_allowed(user_id: int) -> bool:
    """Перевірка, чи користувач у білому списку"""
    return user_id in ALLOWED_USERS
