from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import subprocess
import ctypes
from bot.security.session_manager import is_session_active
from bot.security import is_allowed
from bot.logger import log_action

router = Router()

# Зберігаємо обрану дію для кожного користувача
pending_action = {}

# =========================
# Меню Система
# =========================
@router.message(F.text == "Система")  # Використовуємо точний текст без emoji
async def system_menu(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Shutdown", callback_data="system_Shutdown"),
         InlineKeyboardButton(text="Restart", callback_data="system_Restart")],
        [InlineKeyboardButton(text="Lock", callback_data="system_Lock"),
         InlineKeyboardButton(text="Logoff", callback_data="system_Logoff")]
    ])

    await message.answer("🖥 Виберіть дію з ПК:", reply_markup=kb)

# =========================
# Callback вибору дії
# =========================
@router.callback_query(F.data.startswith("system_"))
async def system_action(call: CallbackQuery):
    user_id = call.from_user.id
    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    action = call.data.split("_")[1]
    pending_action[user_id] = action

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data="system_confirm"),
         InlineKeyboardButton(text="❌ Відмінити", callback_data="system_cancel")]
    ])

    await call.message.edit_text(f"⚠️ Ви обрали {action}. Підтвердьте дію:", reply_markup=confirm_kb)
    await call.answer()

# =========================
# Callback підтвердження/відміни
# =========================
@router.callback_query(F.data.in_({"system_confirm", "system_cancel"}))
async def execute_system_action(call: CallbackQuery):
    user_id = call.from_user.id
    action = pending_action.get(user_id)

    if not action:
        return await call.answer("❌ Немає дії", show_alert=True)

    if call.data == "system_cancel":
        pending_action.pop(user_id, None)
        await call.message.edit_text("❌ Дію скасовано")
        return await call.answer("Дію відмінено")

    # Виконання дії
    try:
        if action == "Shutdown":
            subprocess.run("shutdown /s /t 0", shell=True)
        elif action == "Restart":
            subprocess.run("shutdown /r /t 0", shell=True)
        elif action == "Logoff":
            subprocess.run("shutdown /l", shell=True)
        elif action == "Lock":
            ctypes.windll.user32.LockWorkStation()

        log_action(user_id, f"Система: {action} виконана")
        await call.message.edit_text(f"✅ Дію {action} виконано")
    except Exception as e:
        log_action(user_id, f"Система: {action} не вдалося", str(e))
        await call.message.edit_text(f"❌ Помилка виконання {action}")

    pending_action.pop(user_id, None)
    await call.answer()
