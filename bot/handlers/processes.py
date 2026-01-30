from aiogram import Router
from aiogram.types import Message
import psutil
from bot.security import is_allowed, is_session_active
from bot.logger import log_action
from bot.utils import is_command

router = Router()

@router.message(lambda message: is_command(message.text, "Процеси"))
async def list_processes(message: Message):
    if not is_allowed(message.from_user.id):
        log_action(message.from_user.id, "Спроба доступу до Процеси", "Заборонено")
        return await message.answer("⛔ Доступ заборонено")

    if not is_session_active(message.from_user.id):
        log_action(message.from_user.id, "Спроба доступу до Процеси", "Сесія завершена")
        return await message.answer("🔒 Сесія завершена")

    log_action(message.from_user.id, "Перегляд списку процесів")

    # Отримуємо список процесів
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Сортування по CPU (спадання)
    procs_cpu = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:10]
    # Сортування по RAM (спадання)
    procs_ram = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:10]

    msg = "💻 Топ 10 процесів по CPU:\n"
    for p in procs_cpu:
        msg += f"{p['name']} (PID {p['pid']}) - CPU: {p['cpu_percent']}%, RAM: {p['memory_percent']:.1f}%\n"

    msg += "\n🧠 Топ 10 процесів по RAM:\n"
    for p in procs_ram:
        msg += f"{p['name']} (PID {p['pid']}) - CPU: {p['cpu_percent']}%, RAM: {p['memory_percent']:.1f}%\n"

    await message.answer(msg)
