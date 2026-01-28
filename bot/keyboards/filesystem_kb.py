from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

filesystem_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📁 Переглянути директорії", callback_data="fs_list")],
    [InlineKeyboardButton(text="🗑 Завантажити / Видалити файли", callback_data="fs_upload_delete")],
    [InlineKeyboardButton(text="🔍 Пошук файлів", callback_data="fs_search")],
    [InlineKeyboardButton(text="🗂 Архів / Резервне копіювання", callback_data="fs_archive")],
    [InlineKeyboardButton(text="🔒 Обмеження доступу до системних папок", callback_data="fs_restrict")],
])
