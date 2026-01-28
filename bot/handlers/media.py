from aiogram import Router, F
from aiogram.types import Message
from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()

@router.message(F.text == "Медіа")
async def media_menu(message: Message):
    if not is_allowed(message.from_user.id):
        log_action(message.from_user.id, "Спроба доступу до Медіа", "Заборонено")
        return await message.answer("⛔ Доступ заборонено")

    if not is_session_active(message.from_user.id):
        log_action(message.from_user.id, "Спроба доступу до Медіа", "Сесія завершена")
        return await message.answer("🔒 Сесія завершена")

    log_action(message.from_user.id, "Відкрито Медіа меню")
    await message.answer(
        "🔊 Медіа-керування\n\n"
        "▶️ Play / Pause\n"
        "🔈 Гучність +/-\n"
        "🔇 Mute\n\n"
        "⚠️ Реалізація на наступному кроці"
    )
