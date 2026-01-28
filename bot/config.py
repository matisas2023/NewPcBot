import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERS = set(map(int, os.getenv("ALLOWED_USERS").split(",")))
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", 300))
