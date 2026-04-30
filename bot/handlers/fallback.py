from aiogram import Router
from aiogram.types import Message
from bot.security import start_session, is_allowed
from bot.keyboards import main_menu
from bot.logger import log_action
from bot.utils import is_allowed_command

router = Router()

_ALLOWED_COMMANDS = {
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
    "Історія",
    "FAQ",
    "Тема",
    "Голос",
    "Досягнення",
    "Вихід",
    "music_status",
    "music_download",
    "music_log",
    "music_restart",
    "music_space",
}


@router.message(lambda message: not is_allowed_command(message.text, _ALLOWED_COMMANDS))
async def fallback_handler(message: Message):
    if not is_allowed(message.from_user.id):
        log_action(message.from_user.id, f"Спроба доступу до невідомої команди: {message.text}", "Заборонено")
        return await message.answer("⛔ Доступ заборонено")

    start_session(message.from_user.id)
    log_action(message.from_user.id, f"Невідома команда: {message.text}", "Показано головне меню")
    await message.answer("Головне меню:", reply_markup=main_menu)
