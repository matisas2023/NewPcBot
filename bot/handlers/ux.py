import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.logger import log_action
from bot.security import is_allowed, is_session_active
from bot.utils import is_command

router = Router()

LOG_PATH = Path("logs/actions.log")
SCREENSHOT_DIR = Path("screenshots")
MAX_ACTIONS = 10
MAX_SCREENSHOTS = 5

theme_preferences: Dict[int, str] = {}
pending_speech: Dict[int, bool] = {}


def get_theme_label(user_id: int) -> str:
    return theme_preferences.get(user_id, "light")


def format_message(user_id: int, text: str) -> str:
    theme = get_theme_label(user_id)
    prefix = "🌙" if theme == "dark" else "☀️"
    return f"{prefix} {text}"


def read_last_actions(user_id: int, limit: int = MAX_ACTIONS) -> List[str]:
    if not LOG_PATH.exists():
        return []

    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    user_lines = [line for line in lines if f"User {user_id}" in line]
    return user_lines[-limit:]


def format_screenshot_history() -> List[str]:
    if not SCREENSHOT_DIR.exists():
        return []

    files = sorted(
        [p for p in SCREENSHOT_DIR.iterdir() if p.suffix.lower() == ".png"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    recent = files[:MAX_SCREENSHOTS]
    return [f"{path.name}" for path in recent]


def faq_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Як почати сесію?", callback_data="faq_start")],
        [InlineKeyboardButton(text="🖼 Як отримати скриншот?", callback_data="faq_screenshot")],
        [InlineKeyboardButton(text="📁 Як працює файлова система?", callback_data="faq_files")],
        [InlineKeyboardButton(text="🔔 Як увімкнути автозвіти?", callback_data="faq_autoreport")],
    ])


@router.message(lambda message: is_command(message.text, "FAQ"))
async def faq_menu(message: Message) -> None:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("❓ Часті питання:", reply_markup=faq_keyboard())


@router.callback_query(F.data.startswith("faq_"))
async def faq_answer(call: CallbackQuery) -> None:
    user_id = call.from_user.id
    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    answers = {
        "faq_start": "Натисніть «Старт», щоб почати сесію та побачити головне меню.",
        "faq_screenshot": "Натисніть «Скриншот», щоб отримати поточний екран, або «Оновити» в inline-кнопках.",
        "faq_files": "Оберіть «Файлова система», щоб переглядати папки, шукати або видаляти файли.",
        "faq_autoreport": "Оберіть «Автозвіти» і натисніть «Увімкнути автозвіт».",
    }
    answer = answers.get(call.data, "Немає відповіді для цього пункту.")
    await call.message.answer(answer)
    await call.answer()


@router.message(lambda message: is_command(message.text, "Історія"))
async def history_menu(message: Message) -> None:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    actions = read_last_actions(user_id)
    screenshots = format_screenshot_history()

    actions_block = "\n".join(actions) if actions else "Немає дій для відображення."
    screenshots_block = "\n".join(screenshots) if screenshots else "Скріншотів ще немає."

    await message.answer(
        format_message(
            user_id,
            "🧾 Останні дії:\n"
            f"{actions_block}\n\n"
            "🖼 Останні скриншоти:\n"
            f"{screenshots_block}"
        )
    )
    log_action(user_id, "Перегляд історії дій/скриншотів")


@router.message(lambda message: is_command(message.text, "Тема"))
async def toggle_theme(message: Message) -> None:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    current = get_theme_label(user_id)
    new_theme = "dark" if current == "light" else "light"
    theme_preferences[user_id] = new_theme
    await message.answer(format_message(user_id, f"Тему змінено на {new_theme}."))
    log_action(user_id, "Зміна теми", new_theme)


@router.message(lambda message: is_command(message.text, "Голос"))
async def speech_prompt(message: Message) -> None:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    pending_speech[user_id] = True
    await message.answer("🔊 Надішліть текст, який потрібно озвучити на ПК.")


def speak_text(text: str) -> None:
    safe_text = text.replace("'", "''")
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$speak.Speak('{safe_text}');"
    )
    subprocess.run(
        ["powershell", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )


@router.message(lambda message: message.from_user.id in pending_speech)
async def speech_message(message: Message) -> None:
    user_id = message.from_user.id
    pending_speech.pop(user_id, None)

    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    text = message.text or ""
    if not text.strip():
        return await message.answer("⚠️ Текст порожній")

    try:
        await asyncio.to_thread(speak_text, text)
        log_action(user_id, "TTS повідомлення відправлено", text)
        await message.answer("✅ Голосове повідомлення відтворено на ПК")
    except Exception as exc:
        log_action(user_id, "Помилка TTS", str(exc))
        await message.answer("❌ Не вдалося відтворити TTS на ПК")


@router.message(lambda message: is_command(message.text, "Досягнення"))
async def achievements(message: Message) -> None:
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    action_count = len(read_last_actions(user_id, limit=10000))
    if action_count >= 100:
        badge = "🏆 Легенда"
    elif action_count >= 50:
        badge = "🥇 Профі"
    elif action_count >= 10:
        badge = "🥈 Активний"
    else:
        badge = "🥉 Новачок"

    await message.answer(
        format_message(
            user_id,
            f"{badge}\n"
            f"Дій зафіксовано: {action_count}\n"
            "Продовжуйте користуватися ботом, щоб отримати нові рівні!"
        )
    )
    log_action(user_id, "Перегляд досягнень", f"actions={action_count}")
