# bot/security/allowed_users.py

# Білий список Telegram ID
ALLOWED_USERS = [
    496420361,  # твій Telegram ID
    # додати інших, якщо потрібно
]

def is_allowed(user_id: int) -> bool:
    """Перевірка, чи користувач у білому списку"""
    return user_id in ALLOWED_USERS
