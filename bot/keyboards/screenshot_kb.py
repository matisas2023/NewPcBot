from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

screenshot_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data="screenshot_refresh")
        ]
    ]
)
