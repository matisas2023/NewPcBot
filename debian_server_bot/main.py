import asyncio
import os
import shlex
import subprocess
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DEBIAN_BOT_TOKEN", "")
ALLOWED_USERS = {int(x) for x in os.getenv("DEBIAN_ALLOWED_USERS", "").split(",") if x.strip()}
ALLOWED_CHATS = {int(x) for x in os.getenv("DEBIAN_ALLOWED_CHATS", "").split(",") if x.strip()}

MUSIC_DIR = "/mnt/storage/music"
STORAGE_DIR = "/mnt/storage"
MUSIC_LIMIT_MB = 30720


def is_allowed(message: Message) -> bool:
    user_ok = (not ALLOWED_USERS) or (message.from_user and message.from_user.id in ALLOWED_USERS)
    chat_ok = (not ALLOWED_CHATS) or (message.chat and message.chat.id in ALLOWED_CHATS)
    return user_ok and chat_ok


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


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("DEBIAN_BOT_TOKEN не задано")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer(
            "✅ Debian Bot активний.\n"
            "Команди: /status /diag /disk /fs /top /services /net /reboot /shutdown /lock /restart_service <name>\n"
            "Музика: /music_status /music_download /music_log /music_restart /music_space"
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        host = subprocess.getoutput("hostname")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cpu = subprocess.getoutput("top -bn1 | awk '/Cpu/ {print 100-$8}'")
        ram = subprocess.getoutput("free -m | awk 'NR==2 {printf \"%s/%s MB\", $3,$2}'")
        await message.answer(f"🖥 {host}\n🕒 {now}\n⚙ CPU: {cpu}%\n🧠 RAM: {ram}")

    @dp.message(Command("diag"))
    async def cmd_diag(message: Message):
        if not is_allowed(message):
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
        await message.answer((text[:3900] + "\n...обрізано") if len(text) > 4000 else text)

    @dp.message(Command("disk"))
    async def cmd_disk(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["df", "-h"])
        await message.answer(f"```\n{out[:3800]}\n```" if ok else f"❌ {out}")

    @dp.message(Command("fs"))
    async def cmd_fs(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["ls", "-lah", "/"])
        await message.answer((out[:3900] + "\n...обрізано") if len(out) > 4000 else out)

    @dp.message(Command("top"))
    async def cmd_top(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["ps", "aux", "--sort=-%cpu"])
        await message.answer((out[:3900] + "\n...обрізано") if len(out) > 4000 else out)

    @dp.message(Command("services"))
    async def cmd_services(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "list-units", "--type=service", "--state=running"])
        await message.answer((out[:3900] + "\n...обрізано") if len(out) > 4000 else out)

    @dp.message(Command("net"))
    async def cmd_net(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ip = subprocess.getoutput("hostname -I")
        routes = subprocess.getoutput("ip route")
        await message.answer(f"🌐 IP: {ip}\n\nМаршрути:\n{routes[:3500]}")

    @dp.message(Command("music_status"))
    async def cmd_music_status(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer(render_music_status())

    @dp.message(Command("music_download"))
    async def cmd_music_download(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        try:
            log = open("/var/log/music_manual.log", "a", encoding="utf-8")
            subprocess.Popen(["/usr/local/bin/music_auto_download.sh"], stdout=log, stderr=subprocess.STDOUT)
            await message.answer("🚀 Завантаження музики запущено")
        except Exception as exc:
            await message.answer(f"❌ {exc}")

    @dp.message(Command("music_log"))
    async def cmd_music_log(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["tail", "-n", "40", "/var/log/music_auto_download.log"])
        text = out if ok else f"❌ {out}"
        await message.answer((text[:3900] + "\n...обрізано") if len(text) > 4000 else text)

    @dp.message(Command("music_restart"))
    async def cmd_music_restart(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "restart", "navidrome"])
        if not ok:
            ok, out = run_cmd(["service", "navidrome", "restart"])
        await message.answer("✅ Navidrome перезапущено" if ok else f"❌ {out}")

    @dp.message(Command("music_space"))
    async def cmd_music_space(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["music_status"])
        await message.answer(out if ok else render_music_status())

    @dp.message(Command("reboot"))
    async def cmd_reboot(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "reboot"])
        await message.answer("🔄 Сервер перезавантажується" if ok else f"❌ {out}")

    @dp.message(Command("shutdown"))
    async def cmd_shutdown(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["systemctl", "poweroff"])
        await message.answer("⏻ Сервер вимикається" if ok else f"❌ {out}")

    @dp.message(Command("lock"))
    async def cmd_lock(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        ok, out = run_cmd(["loginctl", "lock-session"])
        await message.answer("🔒 Сесію заблоковано" if ok else f"❌ {out}")

    @dp.message(Command("restart_service"))
    async def cmd_restart_service(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.answer("Використання: /restart_service <service_name>")
        name = parts[1].strip()
        ok, out = run_cmd(["systemctl", "restart", name])
        await message.answer(f"✅ {name} перезапущено" if ok else f"❌ {out}")

    @dp.message(F.text)
    async def fallback(message: Message):
        if not is_allowed(message):
            return await message.answer("⛔ Доступ заборонено")
        await message.answer("Невідома команда. Напишіть /start")

    print("🤖 Debian Server Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
