from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import importlib.util
import os
import sys

from bot.security import is_allowed, is_session_active
from bot.logger import log_action
from bot.utils import is_command

router = Router()

# =========================
# Клавіатура для Медіаплеєра
# =========================
def media_controls_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏯ Play/Pause", callback_data="mediaplayer_playpause"),
            InlineKeyboardButton(text="⏭ Next", callback_data="mediaplayer_next"),
            InlineKeyboardButton(text="⏮ Prev", callback_data="mediaplayer_prev")
        ],
        [
            InlineKeyboardButton(text="🔊 Volume Up", callback_data="mediaplayer_volup"),
            InlineKeyboardButton(text="🔉 Volume Down", callback_data="mediaplayer_voldown"),
            InlineKeyboardButton(text="🔇 Mute", callback_data="mediaplayer_mute")
        ]
    ])
    return kb


def input_controls_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⎋ ESC", callback_data="input_esc"),
            InlineKeyboardButton(text="↵ ENTER", callback_data="input_enter"),
            InlineKeyboardButton(text="ALT+TAB", callback_data="input_alttab"),
        ],
        [
            InlineKeyboardButton(text="🖱 Click", callback_data="input_click"),
        ],
        [
            InlineKeyboardButton(text="⬆️", callback_data="input_move_up"),
            InlineKeyboardButton(text="⬇️", callback_data="input_move_down"),
            InlineKeyboardButton(text="⬅️", callback_data="input_move_left"),
            InlineKeyboardButton(text="➡️", callback_data="input_move_right"),
        ],
    ])
    return kb

# =========================
# Меню Медіаплеєра
# =========================
@router.message(lambda message: is_command(message.text, "Медіаплеєр"))
async def media_controls_menu(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🎛 Управління медіаплеєром:", reply_markup=media_controls_kb())
    log_action(user_id, "Відкрив меню Медіаплеєра")


@router.message(lambda message: is_command(message.text, "Введення"))
async def input_controls_menu(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🎛 Керування введенням:", reply_markup=input_controls_kb())
    log_action(user_id, "Відкрив меню введення")

# =========================
# Ініціалізація COM для Windows Media Player
# =========================
def get_wmp():
    if importlib.util.find_spec("comtypes.client") is None:
        print("❌ Бібліотека comtypes не встановлена")
        return None

    import comtypes.client

    try:
        wmp = comtypes.client.CreateObject("WMPlayer.OCX")
        return wmp
    except Exception as e:
        print("❌ Помилка COM:", e)
        return None


def get_pyautogui():
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return None
    if importlib.util.find_spec("pyautogui") is None:
        return None

    import pyautogui

    return pyautogui

# =========================
# Обробка inline кнопок
# =========================
@router.callback_query(F.data.startswith("mediaplayer_"))
async def media_controls_action(call: CallbackQuery):
    user_id = call.from_user.id

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    action = call.data.replace("mediaplayer_", "")
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


@router.callback_query(F.data.startswith("input_"))
async def input_controls_action(call: CallbackQuery):
    user_id = call.from_user.id

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    action = call.data.replace("input_", "")
    pyautogui = get_pyautogui()
    if pyautogui is None:
        await call.answer("❌ Недоступно в цьому середовищі", show_alert=True)
        return

    try:
        if action == "esc":
            pyautogui.press("esc")
        elif action == "enter":
            pyautogui.press("enter")
        elif action == "alttab":
            pyautogui.hotkey("alt", "tab")
        elif action == "click":
            pyautogui.click()
        elif action == "move_up":
            pyautogui.moveRel(0, -50)
        elif action == "move_down":
            pyautogui.moveRel(0, 50)
        elif action == "move_left":
            pyautogui.moveRel(-50, 0)
        elif action == "move_right":
            pyautogui.moveRel(50, 0)
        else:
            return await call.answer("❌ Невідома дія", show_alert=True)

        log_action(user_id, f"Input action executed: {action}")
        await call.answer("✅ Виконано")
    except Exception as e:
        log_action(user_id, f"Input action error: {action}", str(e))
        await call.answer("❌ Помилка виконання", show_alert=True)
