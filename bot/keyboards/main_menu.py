from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Старт")],
        [KeyboardButton(text="Статус ПК"), KeyboardButton(text="Скриншот")],
        [KeyboardButton(text="Система"), KeyboardButton(text="Медіа")],
        [KeyboardButton(text="Процеси"), KeyboardButton(text="Файлова система")],  # <- нова кнопка
        [KeyboardButton(text="Вихід")],
    ],
    resize_keyboard=True
)
