from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import os
import shutil
import zipfile
from datetime import datetime
from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()

# =========================
# Меню файлової системи
# =========================
def filesystem_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📁 Переглянути директорії", callback_data="fs_list")],
            [InlineKeyboardButton(text="📤 Завантажити файл", callback_data="fs_upload")],
            [InlineKeyboardButton(text="🗑 Видалити файл", callback_data="fs_delete")],
            [InlineKeyboardButton(text="🔍 Пошук файлів", callback_data="fs_search")],
            [InlineKeyboardButton(text="🗂 Архівація", callback_data="fs_archive")],
            [InlineKeyboardButton(text="💾 Резервне копіювання", callback_data="fs_backup")],
        ]
    )

# =========================
# Відкриття меню
# =========================
@router.message(F.text == "Файлова система")
async def fs_menu(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🎛 Меню файлової системи:", reply_markup=filesystem_menu_kb())
    log_action(user_id, "Відкрито меню файлової системи")

# =========================
# Обробка вибору дії
# =========================
@router.callback_query(F.data.startswith("fs_"))
async def fs_actions(call: CallbackQuery):
    user_id = call.from_user.id
    action = call.data.replace("fs_", "")

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    if action == "list":
        dirs = "\n".join(os.listdir('.'))
        await call.message.edit_text(f"📂 Вміст директорії:\n{dirs or 'Порожньо'}")
    elif action == "upload":
        await call.message.edit_text("📤 Відправте файл у відповідь на це повідомлення для завантаження.")
    elif action == "delete":
        await call.message.edit_text("🗑 Введіть шлях до файлу для видалення.")
    elif action == "search":
        await call.message.edit_text("🔍 Введіть ім'я або розширення файлу для пошуку.")
    elif action == "archive":
        archive_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        with zipfile.ZipFile(archive_name, 'w') as zipf:
            for file in os.listdir('.'):
                if os.path.isfile(file):
                    zipf.write(file)
        await call.message.edit_text(f"🗂 Архів створено: {archive_name}")
    elif action == "backup":
        backup_dir = "backup"
        os.makedirs(backup_dir, exist_ok=True)
        for file in os.listdir('.'):
            if os.path.isfile(file):
                shutil.copy(file, backup_dir)
        await call.message.edit_text(f"💾 Резервне копіювання завершено в папку: {backup_dir}")

    log_action(user_id, f"Файлова система: {action} виконано")
    await call.answer()
