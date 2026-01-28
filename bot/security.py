import time

# ===== Білий список Telegram ID =====
ALLOWED_USERS = [496420361]  # заміни на свій Telegram ID

# ===== Сесії користувачів =====
_sessions = {}  # user_id: last_activity_timestamp
SESSION_TIMEOUT = 10 * 60  # 10 хвилин у секундах

# ===== Перевірка дозволених користувачів =====
def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

# ===== Старт сесії =====
def start_session(user_id: int):
    _sessions[user_id] = time.time()

# ===== Перевірка активної сесії =====
def is_session_active(user_id: int) -> bool:
    ts = _sessions.get(user_id)
    if not ts:
        return False
    if time.time() - ts > SESSION_TIMEOUT:
        _sessions.pop(user_id)
        return False
    # оновлюємо час активності
    _sessions[user_id] = time.time()
    return True

# ===== Завершення сесії =====
def end_session(user_id: int):
    if user_id in _sessions:
        _sessions.pop(user_id)
