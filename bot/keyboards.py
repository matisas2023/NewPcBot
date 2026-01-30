from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# Головне меню
# =========================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Старт")],
        [KeyboardButton(text="Статус ПК"), KeyboardButton(text="Скриншот")],
        [KeyboardButton(text="Система"), KeyboardButton(text="Медіа")],
        [KeyboardButton(text="Процеси"), KeyboardButton(text="Файлова система")],
        [KeyboardButton(text="Медіаплеєр"), KeyboardButton(text="Введення")],
        [KeyboardButton(text="Автозвіти")],
        [KeyboardButton(text="Вихід")],
    ],
    resize_keyboard=False
)

# =========================
# Inline клавіатури
# =========================
screenshot_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оновити", callback_data="screenshot_refresh")]
    ]
)

confirm_system_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data="system_confirm"),
         InlineKeyboardButton(text="❌ Відмінити", callback_data="system_cancel")]
    ]
)
