from aiogram import Router, F
from aiogram.types import Message
from bot.security import start_session, is_allowed
from bot.keyboards import main_menu
from bot.logger import log_action

router = Router()

@router.message(~F.text.in_([
    "Старт",
    "Статус ПК",
    "Скриншот",
    "Система",
    "Медіа",
    "Процеси",
    "Медіаплеєр",
    "Файлова система",
    "Введення",
    "Автозвіти",
    "Вихід"
]))
async def fallback_handler(message: Message):
    if not is_allowed(message.from_user.id):
        log_action(message.from_user.id, f"Спроба доступу до невідомої команди: {message.text}", "Заборонено")
        return await message.answer("⛔ Доступ заборонено")

    start_session(message.from_user.id)
    log_action(message.from_user.id, f"Невідома команда: {message.text}", "Показано головне меню")
    await message.answer("Головне меню:", reply_markup=main_menu)
