# bot/security/session_manager.py

import time

SESSION_TIMEOUT = 10 * 60  # 10 хвилин

active_sessions = {}

def start_session(user_id: int):
    active_sessions[user_id] = time.time()

def end_session(user_id: int):
    active_sessions.pop(user_id, None)

def is_session_active(user_id: int) -> bool:
    last_activity = active_sessions.get(user_id)
    if not last_activity:
        return False
    if time.time() - last_activity > SESSION_TIMEOUT:
        end_session(user_id)
        return False
    # оновлюємо час останньої активності
    active_sessions[user_id] = time.time()
    return True
