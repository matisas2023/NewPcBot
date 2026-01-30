from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import os
import shutil
import zipfile
from datetime import datetime
import re
from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()
pending_action: dict[int, str] = {}
pending_delete_path: dict[int, str] = {}
MAX_SEARCH_RESULTS = 20
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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
        dirs = "\n".join(os.listdir("."))
        await call.message.edit_text(f"📂 Вміст директорії:\n{dirs or 'Порожньо'}")
    elif action == "upload":
        pending_action[user_id] = "upload"
        await call.message.edit_text("📤 Відправте файл у відповідь на це повідомлення для завантаження.")
    elif action == "delete":
        pending_action[user_id] = "delete"
        await call.message.edit_text("🗑 Введіть шлях до файлу для видалення.")
    elif action == "search":
        pending_action[user_id] = "search"
        await call.message.edit_text("🔍 Введіть ім'я або розширення файлу для пошуку.")
    elif action == "archive":
        archive_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        with zipfile.ZipFile(archive_name, "w") as zipf:
            for file in os.listdir("."):
                if os.path.isfile(file):
                    zipf.write(file)
        await call.message.edit_text(f"🗂 Архів створено: {archive_name}")
    elif action == "backup":
        backup_dir = "backup"
        os.makedirs(backup_dir, exist_ok=True)
        for file in os.listdir("."):
            if os.path.isfile(file):
                shutil.copy(file, backup_dir)
        await call.message.edit_text(f"💾 Резервне копіювання завершено в папку: {backup_dir}")

    log_action(user_id, f"Файлова система: {action} виконано")
    await call.answer()


@router.message(F.document)
async def fs_upload_document(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    if pending_action.get(user_id) != "upload":
        return

    document = message.document
    filename = os.path.basename(document.file_name)
    destination = filename
    if os.path.exists(destination):
        name, ext = os.path.splitext(filename)
        destination = f"{name}_{int(datetime.now().timestamp())}{ext}"

    await message.bot.download(document, destination=destination)
    pending_action.pop(user_id, None)
    log_action(user_id, f"Файл завантажено: {destination}")
    await message.answer(f"✅ Файл збережено як: {destination}")


@router.message(F.text)
async def fs_text_input(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    action = pending_action.get(user_id)
    if not action:
        return

    text = message.text.strip()

    if action == "delete":
        file_path = text
        if not os.path.isfile(file_path):
            await message.answer("❌ Файл не знайдено. Спробуйте ще раз.")
            return

        pending_delete_path[user_id] = file_path
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Підтвердити", callback_data="fs_delete_confirm"),
                    InlineKeyboardButton(text="❌ Скасувати", callback_data="fs_delete_cancel"),
                ]
            ]
        )
        await message.answer(
            f"⚠️ Видалити файл: {file_path}?",
            reply_markup=confirm_kb,
        )
        return

    if action == "search":
        results = search_files(text)
        pending_action.pop(user_id, None)
        if results:
            formatted = "\n".join(results)
            await message.answer(f"🔍 Знайдені файли:\n{formatted}")
        else:
            await message.answer("🔍 Нічого не знайдено.")
        log_action(user_id, f"Пошук файлів: {text}")


@router.callback_query(F.data.in_({"fs_delete_confirm", "fs_delete_cancel"}))
async def fs_delete_confirm(call: CallbackQuery):
    user_id = call.from_user.id
    file_path = pending_delete_path.get(user_id)

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    if not file_path:
        return await call.answer("❌ Файл не обрано", show_alert=True)

    if call.data == "fs_delete_cancel":
        pending_delete_path.pop(user_id, None)
        pending_action.pop(user_id, None)
        await call.message.edit_text("❌ Видалення скасовано")
        return await call.answer()

    try:
        os.remove(file_path)
        log_action(user_id, f"Файл видалено: {file_path}")
        await call.message.edit_text(f"✅ Файл видалено: {file_path}")
    except OSError as exc:
        log_action(user_id, f"Помилка видалення: {file_path}", str(exc))
        await call.message.edit_text("❌ Не вдалося видалити файл.")
    finally:
        pending_delete_path.pop(user_id, None)
        pending_action.pop(user_id, None)

    await call.answer()


def search_files(query: str) -> list[str]:
    results: list[str] = []
    query_lower = query.lower()
    search_date = None

    if DATE_PATTERN.match(query_lower):
        search_date = datetime.strptime(query_lower, "%Y-%m-%d").date()

    for root, _, files in os.walk("."):
        for file_name in files:
            if search_date:
                file_path = os.path.join(root, file_name)
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
                if mtime != search_date:
                    continue
            else:
                if query_lower not in file_name.lower():
                    continue

            results.append(os.path.join(root, file_name))
            if len(results) >= MAX_SEARCH_RESULTS:
                return results

    return results
