import asyncio
import ctypes
from dataclasses import dataclass
from typing import Dict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from agent.status import get_status
from bot.config import (
    REPORT_INTERVAL_SECONDS,
    CPU_ALERT_THRESHOLD,
    RAM_ALERT_THRESHOLD,
    DISK_ALERT_THRESHOLD,
)
from bot.logger import log_action
from bot.security import is_allowed, is_session_active
from bot.utils import is_command

router = Router()

@dataclass
class ThresholdState:
    cpu: bool = False
    ram: bool = False
    disk: bool = False


auto_report_tasks: Dict[int, asyncio.Task] = {}
threshold_states: Dict[int, ThresholdState] = {}


def autoreport_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶️ Увімкнути автозвіт", callback_data="autoreport_start"),
            InlineKeyboardButton(text="⏹ Вимкнути автозвіт", callback_data="autoreport_stop"),
        ],
        [
            InlineKeyboardButton(text="📊 Надіслати зараз", callback_data="autoreport_send"),
            InlineKeyboardButton(text="💬 Popup на ПК", callback_data="autoreport_popup"),
        ],
    ])


def format_status(status: dict) -> str:
    return (
        "📊 Автозвіт\n"
        f"🖥 {status['pc']}\n"
        f"⚙ CPU: {status['cpu']}%\n"
        f"🧠 RAM: {status['ram']}%\n"
        f"💾 Disk: {status['disk']}%\n"
        f"⏱ Uptime: {status['uptime']} сек"
    )


def get_threshold_state(user_id: int) -> ThresholdState:
    state = threshold_states.get(user_id)
    if not state:
        state = ThresholdState()
        threshold_states[user_id] = state
    return state


async def send_report(bot, chat_id: int, user_id: int) -> None:
    status = get_status()
    await bot.send_message(chat_id, format_status(status))
    log_action(user_id, "Автозвіт надіслано", f"CPU={status['cpu']} RAM={status['ram']} Disk={status['disk']}")
    await send_threshold_alerts(bot, chat_id, user_id, status)


async def send_threshold_alerts(bot, chat_id: int, user_id: int, status: dict) -> None:
    state = get_threshold_state(user_id)
    cpu_over = status["cpu"] >= CPU_ALERT_THRESHOLD
    ram_over = status["ram"] >= RAM_ALERT_THRESHOLD
    disk_over = status["disk"] >= DISK_ALERT_THRESHOLD

    alerts = []
    if cpu_over and not state.cpu:
        alerts.append(f"⚠️ CPU перевищив {CPU_ALERT_THRESHOLD}% (зараз {status['cpu']}%)")
    if ram_over and not state.ram:
        alerts.append(f"⚠️ RAM перевищив {RAM_ALERT_THRESHOLD}% (зараз {status['ram']}%)")
    if disk_over and not state.disk:
        alerts.append(f"⚠️ Disk перевищив {DISK_ALERT_THRESHOLD}% (зараз {status['disk']}%)")

    state.cpu = cpu_over
    state.ram = ram_over
    state.disk = disk_over

    if alerts:
        alert_message = "\n".join(alerts)
        await bot.send_message(chat_id, f"🚨 Пороги перевищено:\n{alert_message}")
        log_action(user_id, "Push-сповіщення про пороги", alert_message)


async def autoreport_loop(bot, chat_id: int, user_id: int) -> None:
    try:
        while True:
            await send_report(bot, chat_id, user_id)
            await asyncio.sleep(REPORT_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        return


@router.message(lambda message: is_command(message.text, "Автозвіти"))
async def autoreport_menu(message: Message) -> None:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🔔 Автозвіти та push-сповіщення:", reply_markup=autoreport_keyboard())


@router.callback_query(F.data.in_({"autoreport_start", "autoreport_stop", "autoreport_send", "autoreport_popup"}))
async def autoreport_actions(call: CallbackQuery) -> None:
    user_id = call.from_user.id
    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    if call.data == "autoreport_start":
        if user_id in auto_report_tasks:
            return await call.answer("✅ Автозвіт уже увімкнено", show_alert=True)
        task = asyncio.create_task(autoreport_loop(call.bot, call.message.chat.id, user_id))
        auto_report_tasks[user_id] = task
        log_action(user_id, "Автозвіт увімкнено")
        await call.message.answer("✅ Автозвіт увімкнено")
        return await call.answer()

    if call.data == "autoreport_stop":
        task = auto_report_tasks.pop(user_id, None)
        if task:
            task.cancel()
        threshold_states.pop(user_id, None)
        log_action(user_id, "Автозвіт вимкнено")
        await call.message.answer("⏹ Автозвіт вимкнено")
        return await call.answer()

    if call.data == "autoreport_send":
        await send_report(call.bot, call.message.chat.id, user_id)
        return await call.answer("📊 Звіт надіслано")

    if call.data == "autoreport_popup":
        pending_popup[user_id] = True
        await call.message.answer("✍️ Надішліть текст для popup на ПК")
        return await call.answer()


pending_popup: Dict[int, bool] = {}


@router.message(lambda message: message.from_user.id in pending_popup)
async def popup_message(message: Message) -> None:
    user_id = message.from_user.id
    pending_popup.pop(user_id, None)

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    text = message.text or ""
    if not text.strip():
        return await message.answer("⚠️ Текст порожній")

    try:
        ctypes.windll.user32.MessageBoxW(0, text, "Повідомлення від Telegram-бота", 0)
        log_action(user_id, "Popup повідомлення відправлено", text)
        await message.answer("✅ Popup показано на ПК")
    except Exception as exc:
        log_action(user_id, "Помилка popup", str(exc))
        await message.answer("❌ Не вдалося показати popup")
