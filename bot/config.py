import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
_allowed_users_raw = os.getenv("ALLOWED_USERS", "").strip()
ALLOWED_USERS = (
    set(map(int, _allowed_users_raw.split(","))) if _allowed_users_raw else set()
)
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", 300))
