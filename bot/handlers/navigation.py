"""Navigation is processed before pending text/FSM handlers."""
from aiogram import BaseMiddleware, Router
from bot.keyboards import main_menu
from bot.security import is_allowed, is_session_active
from bot.utils import normalize_command

router = Router()
CONTROLS = {'Назад','Скасувати','Головне меню','cancel','back','menu'}
MENU = {b.text for row in main_menu.keyboard for b in row}


def clear_pending(user_id, cancel_scheduled=False):
    from bot.handlers import filesystem, autoreport, ux, system
    filesystem.pending_action.pop(user_id,None)
    filesystem.pending_delete_path.pop(user_id,None)
    autoreport.pending_popup.pop(user_id,None)
    ux.pending_speech.pop(user_id,None)
    if cancel_scheduled:
        task = system.scheduled_tasks.pop(user_id,None)
        if task:
            task.cancel()
        system.pending_action.pop(user_id,None)


class NavigationMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        text = normalize_command(getattr(event,'text',None))
        if event.from_user and (text in CONTROLS or text in MENU or text == 'start'):
            if is_allowed(event.from_user.id):
                state = data.get('state')
                if state:
                    await state.clear()
                # Outer middleware runs after FSM's initial state lookup; refresh its filter data.
                data['raw_state'] = None
                clear_pending(event.from_user.id, text in CONTROLS or text == 'Вихід')
        return await handler(event,data)


@router.message(lambda message: normalize_command(message.text) in CONTROLS)
async def navigation_menu(message):
    if not is_allowed(message.from_user.id):
        return await message.answer('⛔ Доступ заборонено')
    if not is_session_active(message.from_user.id):
        return await message.answer('🔒 Сесія завершена. Натисни «Старт».',reply_markup=main_menu)
    clear_pending(message.from_user.id,True)
    await message.answer('Головне меню. Незавершене введення скасовано.',reply_markup=main_menu)
