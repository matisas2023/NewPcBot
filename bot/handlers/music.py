from __future__ import annotations

import subprocess
from aiogram import Router
from aiogram.types import Message

from bot.logger import log_action
from bot.security import is_allowed, is_session_active
from bot.utils import is_command

router = Router()

MUSIC_DIR = "/mnt/storage/music"
STORAGE_DIR = "/mnt/storage"
MUSIC_LIMIT_MB = 30720
TELEGRAM_LIMIT = 4096


def _ensure_access(message: Message) -> bool:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return False
    return is_session_active(user_id)


def _fallback_music_stats() -> tuple[int, int, int, str]:
    files_proc = subprocess.run(
        ["find", MUSIC_DIR, "-type", "f"],
        capture_output=True,
        text=True,
        check=True,
    )
    file_count = len([line for line in files_proc.stdout.splitlines() if line.strip()])

    du_proc = subprocess.run(["du", "-sm", MUSIC_DIR], capture_output=True, text=True, check=True)
    used_mb = int((du_proc.stdout.split()[0] if du_proc.stdout else "0"))

    free_limit_mb = max(MUSIC_LIMIT_MB - used_mb, 0)

    df_proc = subprocess.run(["df", "-h", STORAGE_DIR], capture_output=True, text=True, check=True)
    lines = [line for line in df_proc.stdout.splitlines() if line.strip()]
    disk_free = lines[-1].split()[3] if len(lines) > 1 else "N/A"

    return file_count, used_mb, free_limit_mb, disk_free


def _render_music_status(file_count: int, used_mb: int, free_limit_mb: int, disk_free: str) -> str:
    status = "✅ OK" if free_limit_mb > 0 else "⚠️ Ліміт вичерпано"
    return (
        "🎵 Статус музичного сервера\n\n"
        f"Файлів: {file_count}\n"
        f"Зайнято: {used_mb} MB\n"
        f"Ліміт: {MUSIC_LIMIT_MB} MB\n"
        f"Залишилось до ліміту: {free_limit_mb} MB\n"
        f"Вільно на диску: {disk_free}\n\n"
        f"Стан: {status}"
    )


@router.message(lambda message: is_command(message.text, "music_status"))
async def music_status_handler(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    try:
        file_count, used_mb, free_limit_mb, disk_free = _fallback_music_stats()
        await message.answer(_render_music_status(file_count, used_mb, free_limit_mb, disk_free))
    except Exception as exc:
        log_action(user_id, "Помилка /music_status", str(exc))
        await message.answer(f"❌ Помилка отримання статусу музики: {exc}")


@router.message(lambda message: is_command(message.text, "music_download"))
async def music_download_handler(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    try:
        log_file = open("/var/log/music_manual.log", "a", encoding="utf-8")
        subprocess.Popen(
            ["/usr/local/bin/music_auto_download.sh"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        await message.answer("🚀 Завантаження музики запущено у фоні. Лог: /var/log/music_manual.log")
    except Exception as exc:
        log_action(user_id, "Помилка /music_download", str(exc))
        await message.answer(f"❌ Не вдалося запустити завантаження: {exc}")


@router.message(lambda message: is_command(message.text, "music_log"))
async def music_log_handler(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    try:
        proc = subprocess.run(
            ["tail", "-n", "40", "/var/log/music_auto_download.log"],
            capture_output=True,
            text=True,
            check=True,
        )
        text = proc.stdout.strip() or "Лог порожній."
        msg = f"📄 Останні 40 рядків /var/log/music_auto_download.log:\n\n{text}"
        if len(msg) > TELEGRAM_LIMIT:
            msg = msg[: TELEGRAM_LIMIT - 30] + "\n\n... (обрізано для Telegram)"
        await message.answer(msg)
    except Exception as exc:
        log_action(user_id, "Помилка /music_log", str(exc))
        await message.answer(f"❌ Не вдалося прочитати лог: {exc}")


@router.message(lambda message: is_command(message.text, "music_restart"))
async def music_restart_handler(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    try:
        try:
            subprocess.run(["systemctl", "restart", "navidrome"], check=True)
            await message.answer("🔄 Navidrome перезапущено через systemctl.")
        except Exception:
            subprocess.run(["service", "navidrome", "restart"], check=True)
            await message.answer("🔄 Navidrome перезапущено через service.")
    except Exception as exc:
        log_action(user_id, "Помилка /music_restart", str(exc))
        await message.answer(f"❌ Не вдалося перезапустити Navidrome: {exc}")


@router.message(lambda message: is_command(message.text, "music_space"))
async def music_space_handler(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    try:
        music_status_proc = subprocess.run(["music_status"], capture_output=True, text=True)
        if music_status_proc.returncode == 0 and music_status_proc.stdout.strip():
            result = music_status_proc.stdout.strip()
            msg = f"🎼 Результат music_status:\n\n{result}"
        else:
            file_count, used_mb, free_limit_mb, disk_free = _fallback_music_stats()
            msg = _render_music_status(file_count, used_mb, free_limit_mb, disk_free)
        if len(msg) > TELEGRAM_LIMIT:
            msg = msg[: TELEGRAM_LIMIT - 30] + "\n\n... (обрізано для Telegram)"
        await message.answer(msg)
    except Exception as exc:
        log_action(user_id, "Помилка /music_space", str(exc))
        await message.answer(f"❌ Не вдалося отримати дані про місце: {exc}")
