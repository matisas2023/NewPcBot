from aiogram import Router, F
from aiogram.types import Message

from agent.status import get_status
from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()

@router.message(F.text == "Статус ПК")
async def status_pc(message: Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ Доступ заборонено")

    if not is_session_active(message.from_user.id):
        return await message.answer("🔒 Сесія завершена")

    # Логування
    log_action(message.from_user.id, "Статус ПК запитаний")

    s = get_status()
    await message.answer(
        f"🖥 {s['pc']}\n"
        f"💻 OS: {s['os']}\n"
        f"⚙ CPU: {s['cpu']}%\n"
        f"🧠 RAM: {s['ram']}%\n"
        f"💾 Disk: {s['disk']}%\n"
        f"🌐 IP: {s['ip']}"
    )
