# bot/security/session_manager.py

import time

from bot.config import SESSION_TIMEOUT

active_sessions = {}

def start_session(user_id: int):
    active_sessions[user_id] = time.time()

def end_session(user_id: int):
    active_sessions.pop(user_id, None)

def is_session_active(user_id: int) -> bool:
    last_activity = active_sessions.get(user_id)
    if not last_activity:
        # Для серверного сценарію (Debian) автоматично відкриваємо сесію
        # при першій команді, щоб бот не "застрягав" у стані
        # "Сесія завершена" після рестарту процесу.
        start_session(user_id)
        return True
    if SESSION_TIMEOUT <= 0:
        active_sessions[user_id] = time.time()
        return True
    if time.time() - last_activity > SESSION_TIMEOUT:
        start_session(user_id)
        return True
    # оновлюємо час останньої активності
    active_sessions[user_id] = time.time()
    return True
