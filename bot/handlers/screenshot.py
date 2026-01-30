from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InputMediaPhoto
from pathlib import Path
import importlib.util
import os
import sys
import time
from PIL import Image

from bot.security import is_allowed, is_session_active
from bot.keyboards import screenshot_kb
from bot.logger import log_action
from bot.utils import is_command

router = Router()

# Папка для скриншотів
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


def take_screenshot() -> Path:
    """Зробити скриншот і зберегти в screenshots/ з унікальним ім'ям"""
    timestamp = int(time.time())
    path = SCREENSHOT_DIR / f"screenshot_{timestamp}.png"
    has_display = sys.platform == "win32" or os.environ.get("DISPLAY")
    if has_display and importlib.util.find_spec("pyautogui") is not None:
        import pyautogui

        pyautogui.screenshot().save(path)
    else:
        Image.new("RGB", (800, 600), color=(0, 0, 0)).save(path)
    return path


# =========================
# Надіслати скриншот
# =========================
@router.message(lambda message: is_command(message.text, "Скриншот"))
async def screenshot_handler(message: Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ Доступ заборонено")

    if not is_session_active(message.from_user.id):
        return await message.answer("🔒 Сесія завершена")

    path = take_screenshot()
    log_action(message.from_user.id, "Скриншот надісланий", f"Файл: {path.name}")

    await message.answer_photo(
        photo=FSInputFile(path),
        caption="📸 Поточний екран",
        reply_markup=screenshot_kb
    )


# =========================
# Оновити скриншот (inline кнопка)
# =========================
@router.callback_query(F.data == "screenshot_refresh")
async def screenshot_refresh(call: CallbackQuery):
    if not is_allowed(call.from_user.id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)

    if not is_session_active(call.from_user.id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    path = take_screenshot()
    log_action(call.from_user.id, "Скриншот оновлений", f"Файл: {path.name}")

    media = InputMediaPhoto(
        media=FSInputFile(path),
        caption="📸 Оновлений екран"
    )

    try:
        await call.message.edit_media(
            media=media,
            reply_markup=screenshot_kb
        )
    except Exception:
        # Якщо повідомлення не можна змінити, просто відправляємо нове
        await call.message.answer_photo(
            photo=FSInputFile(path),
            caption="📸 Оновлений екран",
            reply_markup=screenshot_kb
        )

    await call.answer("🔄 Оновлено")
