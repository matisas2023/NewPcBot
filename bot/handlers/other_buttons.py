from aiogram import Router
from aiogram.types import Message
from bot.logger import log_action
from bot.security import end_session, is_allowed
from bot.utils import is_command

router = Router()

@router.message(lambda message: is_command(message.text, "Вихід"))
async def exit_bot(message: Message):
    if not is_allowed(message.from_user.id):
        log_action(message.from_user.id, "Спроба Виходу", "Заборонено")
        return await message.answer("⛔ Доступ заборонено")

    end_session(message.from_user.id)
    log_action(message.from_user.id, "Завершено сесію")
    await message.answer("❌ Сесія завершена")
