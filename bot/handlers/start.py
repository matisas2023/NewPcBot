from aiogram import Router
from aiogram.types import Message
from bot.security import start_session, end_session, is_allowed
from bot.keyboards import main_menu
from bot.logger import log_action
from bot.utils import is_command

router = Router()


@router.message(lambda message: is_command(message.text, "Старт"))
async def start_handler(message: Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ Доступ заборонено")

    # Запускаємо сесію
    start_session(message.from_user.id)
    log_action(message.from_user.id, "Сесія запущена")

    # Відправляємо повідомлення з головним меню
    await message.answer(
        "✅ Сесія запущена. Оберіть дію:",
        reply_markup=main_menu
    )


@router.message(lambda message: is_command(message.text, "Вихід"))
async def logout_handler(message: Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ Доступ заборонено")

    # Завершуємо сесію
    end_session(message.from_user.id)
    log_action(message.from_user.id, "Сесія завершена")

    await message.answer("✅ Сесія завершена. Для повторного входу натисніть 🚀 Старт")
