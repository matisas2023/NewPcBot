from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import subprocess
import os
from bot.security import is_allowed, is_session_active
from bot.logger import log_action
from bot.utils import is_command


router = Router()

# =========================
# FSM для мультимедіа
# =========================
class MediaRecordStates(StatesGroup):
    screen_seconds = State()
    camera_seconds = State()
    audio_seconds = State()

# =========================
# Inline клавіатура для мультимедіа
# =========================
def media_menu_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖥 Запис екрану", callback_data="media_screen")],
        [InlineKeyboardButton(text="📷 Запис з камери", callback_data="media_camera")],
        [InlineKeyboardButton(text="🎙 Запис аудіо", callback_data="media_audio")],
    ])
    return kb

# =========================
# Відкриття меню мультимедіа
# =========================
@router.message(lambda message: is_command(message.text, "Медіа"))
async def media_menu(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        return await message.answer("⛔ Доступ заборонено")
    if not is_session_active(user_id):
        return await message.answer("🔒 Сесія завершена")

    await message.answer("🎛 Меню Медіа:", reply_markup=media_menu_kb())
    log_action(user_id, "Відкрито меню мультимедіа")

# =========================
# Обробка вибору дії
# =========================
@router.callback_query(F.data.startswith("media_"))
async def media_select(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    action = call.data.replace("media_", "")

    if not is_allowed(user_id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)
    if not is_session_active(user_id):
        return await call.answer("🔒 Сесія завершена", show_alert=True)

    if action == "screen":
        await call.message.edit_text("🖥 Введіть кількість секунд для запису екрану:")
        await state.set_state(MediaRecordStates.screen_seconds)
    elif action == "camera":
        await call.message.edit_text("📷 Введіть кількість секунд для запису з камери:")
        await state.set_state(MediaRecordStates.camera_seconds)
    elif action == "audio":
        await call.message.edit_text("🎙 Введіть кількість секунд для запису аудіо:")
        await state.set_state(MediaRecordStates.audio_seconds)

    await call.answer()

# =========================
# Обробка введення кількості секунд
# =========================
@router.message(MediaRecordStates.screen_seconds)
async def record_screen(message: Message, state: FSMContext):
    try:
        seconds = int(message.text)
        filename = f"screen_{message.from_user.id}.mp4"
        # Виконати запис екрану (Windows, ffmpeg має бути встановлений)
        subprocess.Popen(f'ffmpeg -f gdigrab -framerate 30 -i desktop -t {seconds} {filename}', shell=True)
        await message.answer(f"🖥 Запис екрану на {seconds} секунд розпочато. Файл: {filename}")
        log_action(message.from_user.id, f"Запис екрану {seconds}s")
    except ValueError:
        await message.answer("❌ Будь ласка, введіть число у секундах.")
    await state.clear()

@router.message(MediaRecordStates.camera_seconds)
async def record_camera(message: Message, state: FSMContext):
    try:
        seconds = int(message.text)
        filename = f"camera_{message.from_user.id}.mp4"
        # Запис з камери
        subprocess.Popen(f'ffmpeg -f dshow -i video="Integrated Camera" -t {seconds} {filename}', shell=True)
        await message.answer(f"📷 Запис з камери на {seconds} секунд розпочато. Файл: {filename}")
        log_action(message.from_user.id, f"Запис з камери {seconds}s")
    except ValueError:
        await message.answer("❌ Будь ласка, введіть число у секундах.")
    await state.clear()

@router.message(MediaRecordStates.audio_seconds)
async def record_audio(message: Message, state: FSMContext):
    try:
        seconds = int(message.text)
        filename = f"audio_{message.from_user.id}.wav"
        # Запис аудіо
        subprocess.Popen(f'ffmpeg -f dshow -i audio="Microphone" -t {seconds} {filename}', shell=True)
        await message.answer(f"🎙 Запис аудіо на {seconds} секунд розпочато. Файл: {filename}")
        log_action(message.from_user.id, f"Запис аудіо {seconds}s")
    except ValueError:
        await message.answer("❌ Будь ласка, введіть число у секундах.")
    await state.clear()
