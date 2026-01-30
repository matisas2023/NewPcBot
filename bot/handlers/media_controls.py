import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import comtypes.client

from bot.security import is_allowed, is_session_active
from bot.logger import log_action

router = Router()

# =========================
# Клавіатура для Медіаплеєра
# =========================
def media_controls_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("⏯ Play/Pause", callback_data="media_playpause"),
            InlineKeyboardButton("⏭ Next", callback_data="media_next"),
            InlineKeyboardButton("⏮ Prev", callback_data="media_prev")
        ],
        [
            InlineKeyboardButton("🔊 Volume Up", callback_data="media_volup"),
            InlineKeyboardButton("🔉 Volume Down", callback_data="media_voldown"),
            InlineKeyboardButton("🔇 Mute", callback_data="media_mute")
        ]
    ])
    return kb

# =========================
# Меню Медіаплеєра
# =========================
@router.message(F.text == "Медіаплеєр")
async def media_controls_menu(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🎛 Управління медіаплеєром:", reply_markup=media_controls_kb())
    log_action(user_id, "Відкрив меню Медіаплеєра")

# =========================
# Ініціалізація COM для Windows Media Player
# =========================
def get_wmp():
    try:
        wmp = comtypes.client.CreateObject("WMPlayer.OCX")
        return wmp
    except Exception as e:
        print("❌ Помилка COM:", e)
        return None

# =========================
# Обробка inline кнопок
# =========================
@router.callback_query(F.data.startswith("media_"))
async def media_controls_action(call: CallbackQuery):
    user_id = call.from_user.id

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    action = call.data.replace("media_", "")
    wmp = get_wmp()
    if not wmp:
        await call.answer("❌ Не вдалося підключитися до медіаплеєра", show_alert=True)
        return

    try:
        if action == "playpause":
            state = wmp.controls.currentItem
            if wmp.controls.isAvailable("pause"):
                wmp.controls.pause()
            else:
                wmp.controls.play()
        elif action == "next":
            wmp.controls.next()
        elif action == "prev":
            wmp.controls.previous()
        elif action == "volup":
            vol = min(100, wmp.settings.volume + 10)
            wmp.settings.volume = vol
        elif action == "voldown":
            vol = max(0, wmp.settings.volume - 10)
            wmp.settings.volume = vol
        elif action == "mute":
            wmp.settings.mute = not wmp.settings.mute

        log_action(user_id, f"Media action executed: {action}")
        await call.answer(f"✅ Дія {action} виконана")
    except Exception as e:
        log_action(user_id, f"Media action error: {action}", str(e))
        await call.answer(f"❌ Помилка виконання {action}", show_alert=True)
