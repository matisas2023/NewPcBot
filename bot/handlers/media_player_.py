from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import subprocess

from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()

# =========================
# INLINE клавіатура
# =========================
def media_player_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏯ Play / Pause", callback_data="play_pause")
            ],
            [
                InlineKeyboardButton(text="⏮ Prev", callback_data="prev"),
                InlineKeyboardButton(text="⏭ Next", callback_data="next"),
            ],
            [
                InlineKeyboardButton(text="🔊 +", callback_data="vol_up"),
                InlineKeyboardButton(text="🔉 -", callback_data="vol_down"),
                InlineKeyboardButton(text="🔇 Mute", callback_data="mute"),
            ]
        ]
    )

# =========================
# Меню Медіаплеєра
# =========================
@router.message(F.text == "Медіаплеєр")
async def media_player_menu(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")

    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer(
        "🎵 **Керування медіаплеєром:**",
        reply_markup=media_player_kb()
    )

# =========================
# Callback обробка
# =========================
@router.callback_query(F.data.startswith("player_"))
async def media_player_control(call: CallbackQuery):
    user_id = call.from_user.id

    if not is_allowed(user_id):
        return await call.answer("⛔", show_alert=True)

    if not is_session_active(user_id):
        return await call.answer("🔒", show_alert=True)

    action = call.data.replace("player_", "")

    try:
        if action == "play_pause":
            subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys([char]179)"],
                shell=True
            )

        elif action == "next":
            subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys([char]176)"],
                shell=True
            )

        elif action == "prev":
            subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys([char]177)"],
                shell=True
            )

        elif action == "vol_up":
            subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys([char]175)"],
                shell=True
            )

        elif action == "vol_down":
            subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys([char]174)"],
                shell=True
            )

        elif action == "mute":
            subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                shell=True
            )

        log_action(user_id, f"Media player action: {action}")
        await call.answer("✅ Виконано")

    except Exception as e:
        log_action(user_id, "Media player error", str(e))
        await call.answer("❌ Помилка", show_alert=True)
