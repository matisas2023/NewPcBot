import os
import shlex
import subprocess
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DEBIAN_BOT_TOKEN", "")
ALLOWED_USERS = {int(x) for x in os.getenv("DEBIAN_ALLOWED_USERS", "").split(",") if x.strip()}
ALLOWED_CHATS = {int(x) for x in os.getenv("DEBIAN_ALLOWED_CHATS", "").split(",") if x.strip()}

MUSIC_DIR = "/mnt/storage/music"
STORAGE_DIR = "/mnt/storage"
MUSIC_LIMIT_MB = 30720
TG_LIMIT = 4096
WATCH_SERVICES = ["navidrome", "docker", "ssh", "nginx"]
pending_confirm: dict[int, str] = {}
alert_tasks: dict[int, asyncio.Task] = {}


def is_allowed_ids(user_id: int | None, chat_id: int | None) -> bool:
    user_ok = (not ALLOWED_USERS) or (user_id in ALLOWED_USERS)
    chat_ok = (not ALLOWED_CHATS) or (chat_id in ALLOWED_CHATS)
    return user_ok and chat_ok


def is_allowed_message(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else None
    cid = message.chat.id if message.chat else None
    return is_allowed_ids(uid, cid)


def run_cmd(args: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
        return True, (proc.stdout or proc.stderr or "OK").strip()
    except Exception as exc:
        return False, str(exc)


def render_music_status() -> str:
    files_ok, files_out = run_cmd(["find", MUSIC_DIR, "-type", "f"])
    if not files_ok:
        return f"❌ Помилка читання {MUSIC_DIR}: {files_out}"
    files_count = len([x for x in files_out.splitlines() if x.strip()])

    du_ok, du_out = run_cmd(["du", "-sm", MUSIC_DIR])
    if not du_ok:
        return f"❌ Помилка du: {du_out}"
    used_mb = int(du_out.split()[0]) if du_out else 0

    df_ok, df_out = run_cmd(["df", "-h", STORAGE_DIR])
    disk_free = "N/A"
    if df_ok:
        lines = [l for l in df_out.splitlines() if l.strip()]
        if len(lines) > 1:
            disk_free = lines[-1].split()[3]

    left = max(MUSIC_LIMIT_MB - used_mb, 0)
    return (
        "🎵 Статус музичного сервісу\n\n"
        f"Файлів: {files_count}\n"
        f"Зайнято: {used_mb} MB\n"
        f"Ліміт: {MUSIC_LIMIT_MB} MB\n"
        f"Залишилось до ліміту: {left} MB\n"
        f"Вільно на диску: {disk_free}"
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Діагностика", callback_data="menu_diag"),
             InlineKeyboardButton(text="🖥️ Система", callback_data="menu_system")],
            [InlineKeyboardButton(text="🌐 Мережа", callback_data="menu_net"),
             InlineKeyboardButton(text="📁 Файли", callback_data="menu_fs")],
            [InlineKeyboardButton(text="🧩 Сервіси", callback_data="menu_services"),
             InlineKeyboardButton(text="🚨 Алерти", callback_data="menu_alerts")],
            [InlineKeyboardButton(text="🎵 Музика/Navidrome", callback_data="menu_music")],
        ]
    )


def music_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Статус музики", callback_data="music_status")],
            [InlineKeyboardButton(text="⬇️ Завантажити", callback_data="music_download")],
            [InlineKeyboardButton(text="📜 Лог завантаження", callback_data="music_log")],
            [InlineKeyboardButton(text="🔄 Рестарт Navidrome", callback_data="music_restart")],
            [InlineKeyboardButton(text="💾 Простір", callback_data="music_space")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_home")],
        ]
    )


def system_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Reboot", callback_data="sys_reboot"),
             InlineKeyboardButton(text="⏻ Shutdown", callback_data="sys_shutdown")],
            [InlineKeyboardButton(text="🔒 Lock", callback_data="sys_lock"),
             InlineKeyboardButton(text="🎛 Services", callback_data="sys_services")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_home")],
        ]
    )


def confirm_kb(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"confirm_{action}"),
             InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm_cancel")]
        ]
    )


def services_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🔄 Restart {svc}", callback_data=f"svc_restart_{svc}")]
            for svc in WATCH_SERVICES]
    rows.append([InlineKeyboardButton(text="📋 Оновити статус", callback_data="svc_status_refresh")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_text(message: Message, text: str, code: bool = False) -> None:
    body = f"```{text}```" if code else text
    if len(body) <= TG_LIMIT:
        await message.answer(body)
        return
    chunk = body[: TG_LIMIT - 20]
    await message.answer(chunk + "\n…обрізано")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("DEBIAN_BOT_TOKEN не задано")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)

    async def render_services_status() -> str:
        lines = ["🧩 <b>Статус ключових сервісів</b>"]
        for svc in WATCH_SERVICES:
            ok, out = run_cmd(["systemctl", "is-active", svc])
            state = out.strip() if ok else "unknown"
            icon = "✅" if state == "active" else "❌"
            lines.append(f"{icon} <code>{svc}</code>: <b>{state}</b>")
        return "\n".join(lines)

    async def alert_loop(chat_id: int) -> None:
        while True:
            cpu = float(subprocess.getoutput("top -bn1 | awk '/Cpu/ {print 100-$8}'") or 0)
            ram_pct = float(subprocess.getoutput("free | awk 'NR==2 {print ($3/$2)*100}'") or 0)
            disk_pct = float(subprocess.getoutput("df / | awk 'NR==2 {gsub(\"%\",\"\",$5); print $5}'") or 0)
            issues = []
            if cpu > 90:
                issues.append(f"CPU {cpu:.1f}%")
            if ram_pct > 90:
                issues.append(f"RAM {ram_pct:.1f}%")
            if disk_pct > 90:
                issues.append(f"Disk {disk_pct:.1f}%")
            if issues:
                await bot.send_message(chat_id, "🚨 <b>Пороги перевищено:</b>\n" + "\n".join(f"• {x}" for x in issues), parse_mode="HTML")
            await asyncio.sleep(120)

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer(
            "✅ <b>Debian Bot активний</b>\n\n"
            "Оберіть розділ через кнопки нижче 👇",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        host = subprocess.getoutput("hostname")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cpu = subprocess.getoutput("top -bn1 | awk '/Cpu/ {print 100-$8}'")
        ram = subprocess.getoutput("free -m | awk 'NR==2 {printf \"%s/%s MB\", $3,$2}'")
        await message.answer(
            "🖥️ <b>Статус сервера</b>\n\n"
            f"Хост: <code>{host}</code>\n"
            f"Час: <code>{now}</code>\n"
            f"CPU: <b>{cpu}%</b>\n"
            f"RAM: <b>{ram}</b>",
            parse_mode="HTML",
        )

    @dp.message(Command("diag"))
    async def cmd_diag(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        cmds = [
            "uptime",
            "systemctl is-system-running",
            "df -h /",
            "free -h",
        ]
        out = []
        for c in cmds:
            ok, res = run_cmd(shlex.split(c))
            out.append(f"$ {c}\n{res if ok else 'ERR: ' + res}")
        text = "\n\n".join(out)
        await send_text(message, text, code=True)

    @dp.message(Command("disk"))
    async def cmd_disk(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["df", "-h"])
        await send_text(message, out if ok else f"❌ {out}", code=ok)

    @dp.message(Command("fs"))
    async def cmd_fs(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["ls", "-lah", "/"])
        await send_text(message, out, code=True)

    @dp.message(Command("top"))
    async def cmd_top(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["ps", "aux", "--sort=-%cpu"])
        await send_text(message, out, code=True)

    @dp.message(Command("services"))
    async def cmd_services(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "list-units", "--type=service", "--state=running"])
        await send_text(message, out, code=True)

    @dp.message(Command("net"))
    async def cmd_net(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ip = subprocess.getoutput("hostname -I")
        routes = subprocess.getoutput("ip route")
        await send_text(message, f"🌐 IP: {ip}\n\nМаршрути:\n{routes}", code=True)

    @dp.message(Command("music_status"))
    async def cmd_music_status(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer(render_music_status())

    @dp.message(Command("music_download"))
    async def cmd_music_download(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        try:
            log = open("/var/log/music_manual.log", "a", encoding="utf-8")
            subprocess.Popen(["/usr/local/bin/music_auto_download.sh"], stdout=log, stderr=subprocess.STDOUT)
            await message.answer("🚀 Завантаження музики запущено")
        except Exception as exc:
            await message.answer(f"❌ {exc}")

    @dp.message(Command("music_log"))
    async def cmd_music_log(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["tail", "-n", "40", "/var/log/music_auto_download.log"])
        text = out if ok else f"❌ {out}"
        await send_text(message, text, code=True)

    @dp.message(Command("music_restart"))
    async def cmd_music_restart(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "restart", "navidrome"])
        if not ok:
            ok, out = run_cmd(["service", "navidrome", "restart"])
        await message.answer("✅ Navidrome перезапущено" if ok else f"❌ {out}")

    @dp.message(Command("music_space"))
    async def cmd_music_space(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["music_status"])
        text = out if ok else render_music_status()
        text = text.replace("[0;34m", "").replace("[1;33m", "").replace("[0;32m", "").replace("[0m", "")
        await send_text(message, text)

    @dp.message(Command("menu"))
    async def cmd_menu(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer("🧭 <b>Головне меню</b>", reply_markup=main_menu_kb(), parse_mode="HTML")

    @dp.callback_query(F.data == "menu_home")
    async def cb_menu_home(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await call.message.answer("🧭 <b>Головне меню</b>", reply_markup=main_menu_kb(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data == "sys_reboot")
    async def cb_sys_reboot(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        pending_confirm[call.from_user.id] = "reboot"
        await call.message.answer("⚠️ Підтвердити перезавантаження?", reply_markup=confirm_kb("reboot"))
        await call.answer()

    @dp.callback_query(F.data == "sys_shutdown")
    async def cb_sys_shutdown(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        pending_confirm[call.from_user.id] = "shutdown"
        await call.message.answer("⚠️ Підтвердити вимкнення сервера?", reply_markup=confirm_kb("shutdown"))
        await call.answer()

    @dp.callback_query(F.data.startswith("confirm_"))
    async def cb_confirm(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        if call.data == "confirm_cancel":
            pending_confirm.pop(call.from_user.id, None)
            await call.message.answer("❎ Дію скасовано")
            return await call.answer()
        action = call.data.replace("confirm_", "")
        expected = pending_confirm.get(call.from_user.id)
        if expected != action:
            return await call.answer("Дія протермінована", show_alert=True)
        pending_confirm.pop(call.from_user.id, None)
        if action == "reboot":
            await cmd_reboot(call.message)
        elif action == "shutdown":
            await cmd_shutdown(call.message)
        await call.answer()

    @dp.callback_query(F.data == "sys_lock")
    async def cb_sys_lock(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await cmd_lock(call.message)
        await call.answer()

    @dp.callback_query(F.data == "sys_services")
    async def cb_sys_services(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await cmd_services(call.message)
        await call.answer()

    @dp.callback_query(F.data == "menu_diag")
    async def cb_menu_diag(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        cmds = ["uptime", "systemctl is-system-running", "df -h /", "free -h"]
        out = []
        for c in cmds:
            ok, res = run_cmd(shlex.split(c))
            out.append(f"$ {c}\n{res if ok else 'ERR: ' + res}")
        await send_text(call.message, "\n\n".join(out), code=True)
        await call.answer()

    @dp.callback_query(F.data == "menu_system")
    async def cb_menu_system(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await cmd_status(call.message)
        await call.message.answer("⚙️ <b>Системні дії</b>", reply_markup=system_menu_kb(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data == "menu_net")
    async def cb_menu_net(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        ip = subprocess.getoutput("hostname -I")
        routes = subprocess.getoutput("ip route")
        await send_text(call.message, f"🌐 IP: {ip}\n\nМаршрути:\n{routes}", code=True)
        await call.answer()

    @dp.callback_query(F.data == "menu_fs")
    async def cb_menu_fs(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        _, out = run_cmd(["ls", "-lah", "/"])
        await send_text(call.message, out, code=True)
        await call.answer()

    @dp.callback_query(F.data == "menu_music")
    async def cb_menu_music(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await call.message.answer("🎵 <b>Музичне меню</b>", reply_markup=music_menu_kb(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data == "menu_services")
    async def cb_menu_services(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await call.message.answer(await render_services_status(), reply_markup=services_kb(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data == "svc_status_refresh")
    async def cb_svc_refresh(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await call.message.answer(await render_services_status(), reply_markup=services_kb(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data.startswith("svc_restart_"))
    async def cb_svc_restart(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        svc = call.data.replace("svc_restart_", "")
        ok, out = run_cmd(["systemctl", "restart", svc])
        await call.message.answer(f"✅ {svc} перезапущено" if ok else f"❌ {out}")
        await call.answer()

    @dp.callback_query(F.data == "menu_alerts")
    async def cb_menu_alerts(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        chat_id = call.message.chat.id
        if chat_id in alert_tasks and not alert_tasks[chat_id].done():
            alert_tasks[chat_id].cancel()
            alert_tasks.pop(chat_id, None)
            await call.message.answer("🔕 Алерти вимкнено")
        else:
            alert_tasks[chat_id] = asyncio.create_task(alert_loop(chat_id))
            await call.message.answer("🔔 Алерти увімкнено (кожні 2 хв)")
        await call.answer()

    @dp.callback_query(F.data == "music_status")
    async def cb_music_status(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        await call.message.answer(render_music_status())
        await call.answer()

    @dp.callback_query(F.data == "music_download")
    async def cb_music_download(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        try:
            log = open("/var/log/music_manual.log", "a", encoding="utf-8")
            subprocess.Popen(["/usr/local/bin/music_auto_download.sh"], stdout=log, stderr=subprocess.STDOUT)
            await call.message.answer("🚀 Завантаження музики запущено")
        except Exception as exc:
            await call.message.answer(f"❌ {exc}")
        await call.answer()

    @dp.callback_query(F.data == "music_log")
    async def cb_music_log(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        ok, out = run_cmd(["tail", "-n", "40", "/var/log/music_auto_download.log"])
        await send_text(call.message, out if ok else f"❌ {out}", code=True)
        await call.answer()

    @dp.callback_query(F.data == "music_restart")
    async def cb_music_restart(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        ok, out = run_cmd(["systemctl", "restart", "navidrome"])
        if not ok:
            ok, out = run_cmd(["service", "navidrome", "restart"])
        await call.message.answer("✅ Navidrome перезапущено" if ok else f"❌ {out}")
        await call.answer()

    @dp.callback_query(F.data == "music_space")
    async def cb_music_space(call: CallbackQuery):
        if not is_allowed_ids(call.from_user.id if call.from_user else None, call.message.chat.id if call.message else None):
            return await call.answer("⛔ Доступ заборонено", show_alert=True)
        ok, out = run_cmd(["music_status"])
        text = out if ok else render_music_status()
        text = text.replace("[0;34m", "").replace("[1;33m", "").replace("[0;32m", "").replace("[0m", "")
        await send_text(call.message, text)
        await call.answer()

    @dp.message(Command("reboot"))
    async def cmd_reboot(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "reboot"])
        await message.answer("🔄 Сервер перезавантажується" if ok else f"❌ {out}")

    @dp.message(Command("shutdown"))
    async def cmd_shutdown(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "poweroff"])
        await message.answer("⏻ Сервер вимикається" if ok else f"❌ {out}")

    @dp.message(Command("lock"))
    async def cmd_lock(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["loginctl", "lock-session"])
        await message.answer("🔒 Сесію заблоковано" if ok else f"❌ {out}")

    @dp.message(Command("restart_service"))
    async def cmd_restart_service(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.answer("Використання: /restart_service <service_name>")
        name = parts[1].strip()
        ok, out = run_cmd(["systemctl", "restart", name])
        await message.answer(f"✅ {name} перезапущено" if ok else f"❌ {out}")

    @dp.message(F.text)
    async def fallback(message: Message):
        if not is_allowed_message(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer("Невідома команда. Напишіть /start")

    print("🤖 Debian Server Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
