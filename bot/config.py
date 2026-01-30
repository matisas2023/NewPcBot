import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
_allowed_users_raw = os.getenv("ALLOWED_USERS", "").strip()
ALLOWED_USERS = (
    set(map(int, _allowed_users_raw.split(","))) if _allowed_users_raw else set()
)
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", 300))

REPORT_INTERVAL_SECONDS = int(os.getenv("REPORT_INTERVAL_SECONDS", 300))
CPU_ALERT_THRESHOLD = int(os.getenv("CPU_ALERT_THRESHOLD", 90))
RAM_ALERT_THRESHOLD = int(os.getenv("RAM_ALERT_THRESHOLD", 90))
DISK_ALERT_THRESHOLD = int(os.getenv("DISK_ALERT_THRESHOLD", 90))
