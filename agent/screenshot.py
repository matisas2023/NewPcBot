from aiogram import Router, F
from aiogram.types import Message
import pyautogui
from pathlib import Path
import time
from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()

# Створюємо папку screenshots, якщо не існує
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

@router.message(F.text == "📸 Скриншот")
async def take_screenshot(message: Message):
    if not is_allowed(message.from_user.id):
        log_action(message.from_user.id, "Спроба зробити скриншот", "Заборонено")
        return await message.answer("⛔ Доступ заборонено")

    if not is_session_active(message.from_user.id):
        log_action(message.from_user.id, "Спроба зробити скриншот", "Сесія завершена")
        return await message.answer("🔒 Сесія завершена")

    log_action(message.from_user.id, "Зроблено скриншот")

    # Генеруємо унікальне ім'я файлу
    timestamp = int(time.time())
    filename = SCREENSHOT_DIR / f"screenshot_{timestamp}.png"

    # Робимо скриншот
    screenshot = pyautogui.screenshot()
    screenshot.save(filename)

    # Відправляємо скриншот користувачу
    await message.answer_photo(photo=open(filename, "rb"), caption=f"📸 Скриншот збережено у {filename}")
