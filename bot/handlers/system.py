from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import subprocess
import ctypes
import asyncio
import platform
import getpass

from bot.security import is_allowed, is_session_active
from bot.logger import log_action
from bot.utils import is_command

router = Router()

# =========================
# Зберігаємо обрану дію та відкладені задачі
# =========================
pending_action: dict[int, str] = {}
scheduled_tasks: dict[int, asyncio.Task] = {}

# =========================
# Клавіатури
# =========================
def system_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏻ Shutdown", callback_data="sys_Shutdown"),
            InlineKeyboardButton(text="🔄 Restart", callback_data="sys_Restart"),
        ],
        [
            InlineKeyboardButton(text="🔒 Lock", callback_data="sys_Lock"),
            InlineKeyboardButton(text="🚪 Logoff", callback_data="sys_Logoff"),
        ],
        [
            InlineKeyboardButton(text="😴 Sleep", callback_data="sys_Sleep"),
            InlineKeyboardButton(text="🛌 Hibernate", callback_data="sys_Hibernate"),
        ],
        [
            InlineKeyboardButton(text="⏱ Таймер 10 сек", callback_data="sys_timer_10"),
            InlineKeyboardButton(text="⏱ Таймер 30 сек", callback_data="sys_timer_30"),
        ]
    ])


def system_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити", callback_data="sys_confirm"),
            InlineKeyboardButton(text="❌ Скасувати", callback_data="sys_cancel"),
        ]
    ])

# =========================
# Меню "Система"
# =========================
@router.message(lambda message: is_command(message.text, "Система"))
async def system_menu(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🎛 Керування системою:", reply_markup=system_menu_kb())


# =========================
# Обробка вибору дії
# =========================
@router.callback_query(F.data.startswith("sys_"))
async def system_select(call: CallbackQuery):
    user_id = call.from_user.id

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    data = call.data
    action = None
    delay = 0

    if data.startswith("sys_timer_"):
        delay = int(data.split("_")[-1])
        action = "Shutdown"  # для прикладу ставимо Shutdown по таймеру
        pending_action[user_id] = action
        # Створюємо задачу
        task = asyncio.create_task(schedule_delayed_action(user_id, delay, call.message))
        scheduled_tasks[user_id] = task
        await call.message.edit_text(f"⏳ Дія **{action}** буде виконана через {delay} секунд")
        return await call.answer()

    else:
        action = data.replace("sys_", "")
        pending_action[user_id] = action

        await call.message.edit_text(
            f"⚠️ Ви впевнені, що хочете виконати **{action}**?",
            reply_markup=system_confirm_kb(),
        )
        await call.answer()


# =========================
# Підтвердження / Скасування
# =========================
@router.callback_query(F.data.in_({"sys_confirm", "sys_cancel"}))
async def system_execute(call: CallbackQuery):
    user_id = call.from_user.id
    action = pending_action.get(user_id)

    if not action:
        return await call.answer("❌ Дія відсутня", show_alert=True)

    if call.data == "sys_cancel":
        # Скасовуємо відкладену задачу
        task = scheduled_tasks.get(user_id)
        if task:
            task.cancel()
            scheduled_tasks.pop(user_id, None)

        pending_action.pop(user_id, None)
        await call.message.edit_text("❌ Дію скасовано")
        return await call.answer()

    # Виконуємо дію
    try:
        execute_system_action(action)
        log_action(user_id, f"System action executed: {action}")
        await call.message.edit_text(f"✅ Дію **{action}** виконано")
    except Exception as e:
        log_action(user_id, f"System action error: {action}", str(e))
        await call.message.edit_text(f"❌ Помилка виконання **{action}**")

    pending_action.pop(user_id, None)
    await call.answer()


# =========================
# Функція виконання системної дії
# =========================
def execute_system_action(action: str):
    system_name = platform.system().lower()

    if system_name == "windows":
        if action == "Shutdown":
            subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
        elif action == "Restart":
            subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
        elif action == "Logoff":
            subprocess.run(["shutdown", "/l"], check=True)
        elif action == "Lock":
            ctypes.windll.user32.LockWorkStation()
        elif action == "Sleep":
            ctypes.windll.powrprof.SetSuspendState(False, True, False)
        elif action == "Hibernate":
            ctypes.windll.powrprof.SetSuspendState(True, True, False)
        return

    if system_name == "linux":
        if action == "Shutdown":
            subprocess.run(["systemctl", "poweroff"], check=True)
        elif action == "Restart":
            subprocess.run(["systemctl", "reboot"], check=True)
        elif action == "Logoff":
            subprocess.run(["loginctl", "terminate-user", getpass.getuser()], check=True)
        elif action == "Lock":
            subprocess.run(["loginctl", "lock-session"], check=True)
        elif action == "Sleep":
            subprocess.run(["systemctl", "suspend"], check=True)
        elif action == "Hibernate":
            subprocess.run(["systemctl", "hibernate"], check=True)
        return

    raise RuntimeError(f"Непідтримувана ОС для системної дії: {system_name}")


# =========================
# Відкладена дія (таймер)
# =========================
async def schedule_delayed_action(user_id: int, delay: int, message: Message):
    try:
        await asyncio.sleep(delay)
        action = pending_action.get(user_id)
        if action:
            execute_system_action(action)
            log_action(user_id, f"Delayed action executed: {action}")
            await message.edit_text(f"✅ Дію **{action}** виконано через {delay} секунд")
            pending_action.pop(user_id, None)
            scheduled_tasks.pop(user_id, None)
    except asyncio.CancelledError:
        # Таймер скасовано
        await message.edit_text("❌ Відкладену дію скасовано")
