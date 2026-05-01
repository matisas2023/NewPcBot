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
        [KeyboardButton(text="Автозвіти"), KeyboardButton(text="Музика")],
        [KeyboardButton(text="Сервіси")],
        [KeyboardButton(text="Історія"), KeyboardButton(text="FAQ")],
        [KeyboardButton(text="Тема"), KeyboardButton(text="Голос"), KeyboardButton(text="Досягнення")],
        [KeyboardButton(text="Вихід")],
    ],
    resize_keyboard=True
)

# =========================
# Inline клавіатури
# =========================
screenshot_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оновити", callback_data="screenshot_refresh")]
    ]
)
