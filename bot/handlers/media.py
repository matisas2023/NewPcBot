"""Explicit capture with device discovery, completion delivery and owner-bound stop."""
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from agent.media_capture import service, CaptureError
from bot.security import is_allowed, is_session_active
from bot.logger import log_action
from bot.utils import is_command

router = Router()

class MediaRecordStates(StatesGroup):
    screen_seconds = State()
    camera_seconds = State()
    audio_seconds = State()

def media_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🖥 Запис екрана',callback_data='media_screen')],
        [InlineKeyboardButton(text='📷 Запис камери',callback_data='media_camera')],
        [InlineKeyboardButton(text='🎙 Запис аудіо',callback_data='media_audio')],
        [InlineKeyboardButton(text='📸 Кадр камери',callback_data='media_view_camera'),
         InlineKeyboardButton(text='🖼 Кадр екрана',callback_data='media_view_screen')]])

def allowed(user_id):
    return is_allowed(user_id) and is_session_active(user_id)

@router.message(lambda message: is_command(message.text,'Медіа'))
async def media_menu(message: Message):
    if not is_allowed(message.from_user.id):return await message.answer('⛔ Доступ заборонено')
    if not is_session_active(message.from_user.id):return await message.answer('🔒 Сесія завершена')
    await message.answer('🎛 Камера, екран і мікрофон. Відео без звуку; запис 1–120 секунд. Готовий файл надійде сюди.',reply_markup=media_menu_kb())
    log_action(message.from_user.id,'Відкрито меню мультимедіа')

@router.callback_query(F.data.in_({'media_screen','media_camera','media_audio'}))
async def media_select(call: CallbackQuery,state: FSMContext):
    if not allowed(call.from_user.id):return await call.answer('⛔ Доступ заборонено або сесія завершена',show_alert=True)
    action=call.data.removeprefix('media_')
    await call.answer()
    if action=='camera':
        try:devices=await asyncio.to_thread(service.devices)
        except CaptureError as exc:return await call.message.answer(str(exc))
        if not devices['cameras']:return await call.message.answer('Камеру не знайдено. Перевір підключення й доступ у Windows.')
        await state.clear()
        keyboard=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=d['name'],callback_data=f'media_device_{d["id"]}')] for d in devices['cameras']])
        return await call.message.answer('Обери камеру:',reply_markup=keyboard)
    await state.set_state(MediaRecordStates.screen_seconds if action=='screen' else MediaRecordStates.audio_seconds)
    await call.message.edit_text('Введи тривалість запису: від 1 до 120 секунд. «Скасувати» — повернення до меню.')

@router.callback_query(F.data.startswith('media_device_'))
async def camera_selected(call: CallbackQuery,state: FSMContext):
    if not allowed(call.from_user.id):return await call.answer('⛔ Сесія завершена',show_alert=True)
    try:
        index=int(call.data.removeprefix('media_device_'))
        await asyncio.to_thread(service.device,'cameras',index)
    except (ValueError,CaptureError) as exc:return await call.answer(str(exc),show_alert=True)
    await state.set_state(MediaRecordStates.camera_seconds)
    await state.update_data(camera=index)
    await call.answer()
    await call.message.answer('Введи тривалість запису камери: 1–120 секунд.')

async def record(message,state,source):
    user=message.from_user.id
    if not allowed(user):return await message.answer('⛔ Доступ заборонено або сесія завершена')
    try:
        seconds=int(message.text or '')
        if not 1<=seconds<=120:raise ValueError()
    except ValueError:return await message.answer('Введи ціле число від 1 до 120. Або натисни «Скасувати».')
    data=await state.get_data()
    owner=f'tg:{user}'
    try:job=await asyncio.to_thread(service.start,source,seconds,owner,data.get('camera',0))
    except CaptureError as exc:return await message.answer('❌ '+str(exc))
    await state.clear()
    stop=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⏹ Зупинити та зберегти',callback_data='media_stop_'+job['id'])]])
    await message.answer(f'🔴 Запис розпочато, до {seconds} с. Готовий файл буде надіслано після завершення.',reply_markup=stop)
    try:
        while job['status']=='recording':
            await asyncio.sleep(0.5)
            if not allowed(user):
                await asyncio.to_thread(service.stop,job['id'],owner)
                return
            job=await asyncio.to_thread(service.get,job['id'],owner)
        if job['status']!='ready':return await message.answer('❌ '+job.get('error','Запис не вдався'))
        path=await asyncio.to_thread(service.file,job['id'],owner)
        if source=='audio':await message.answer_audio(audio=FSInputFile(path),caption='🎙 Готовий запис мікрофона')
        else:await message.answer_video(video=FSInputFile(path),caption='✅ Готовий запис '+('екрана' if source=='screen' else 'камери'),supports_streaming=True)
        log_action(user,'Запис мультимедіа завершено',source)
    except asyncio.CancelledError:
        await asyncio.to_thread(service.stop,job['id'],owner)
        raise
    except Exception:
        await message.answer('Не вдалося надіслати файл. Запис збережено на ПК у .pc-helper-runtime/media.')

@router.message(MediaRecordStates.screen_seconds)
async def record_screen(message: Message,state: FSMContext):await record(message,state,'screen')

@router.message(MediaRecordStates.camera_seconds)
async def record_camera(message: Message,state: FSMContext):await record(message,state,'camera')

@router.message(MediaRecordStates.audio_seconds)
async def record_audio(message: Message,state: FSMContext):await record(message,state,'audio')

@router.callback_query(F.data.startswith('media_stop_'))
async def stop_recording(call: CallbackQuery):
    if not allowed(call.from_user.id):return await call.answer('⛔ Сесія завершена',show_alert=True)
    try:await asyncio.to_thread(service.stop,call.data.removeprefix('media_stop_'),f'tg:{call.from_user.id}')
    except CaptureError as exc:return await call.answer(str(exc),show_alert=True)
    await call.answer('Запис зупиняється; файл буде надіслано')

@router.callback_query(F.data.in_({'media_view_screen','media_view_camera'}))
async def preview(call: CallbackQuery):
    if not allowed(call.from_user.id):return await call.answer('⛔ Сесія завершена',show_alert=True)
    source=call.data.removeprefix('media_view_')
    await call.answer('Отримую кадр…')
    try:
        data=await asyncio.to_thread(service.snapshot,source)
        await call.message.answer_photo(photo=BufferedInputFile(data,filename=source+'.jpg'),caption='Поточний кадр '+('камери' if source=='camera' else 'екрана'))
    except CaptureError as exc:await call.message.answer('❌ '+str(exc))
