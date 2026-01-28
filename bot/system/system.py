from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from bot.security import is_allowed
from bot.security.session_manager import is_session_active
from bot.system.scheduler import schedule_action, cancel_scheduled_action
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


router = Router()

# =========================
# INLINE: SYSTEM MENU
# =========================

system_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔻 Shutdown", callback_data="system_Shutdown"),
            InlineKeyboardButton(text="🔄 Restart", callback_data="system_Restart"),
        ],
        [
            InlineKeyboardButton(text="💤 Sleep", callback_data="system_Sleep"),
            InlineKeyboardButton(text="🛌 Hibernate", callback_data="system_Hibernate"),
        ],
        [
            InlineKeyboardButton(text="🔒 Lock", callback_data="system_Lock"),
            InlineKeyboardButton(text="🚪 Logoff", callback_data="system_Logoff"),
        ],
        [
            InlineKeyboardButton(text="❌ Назад", callback_data="system_back"),
        ],
    ]
)

# =========================
# INLINE: DELAY MENU
# =========================

def delay_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏱ 5 хв", callback_data=f"delay_{action}_300"
                ),
                InlineKeyboardButton(
                    text="⏱ 10 хв", callback_data=f"delay_{action}_600"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏱ 30 хв", callback_data=f"delay_{action}_1800"
                ),
                InlineKeyboardButton(
                    text="⏱ 60 хв", callback_data=f"delay_{action}_3600"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Скасувати", callback_data="delay_cancel"
                )
            ],
        ]
    )

# =========================
# SYSTEM BUTTON (ReplyKeyboard)
# =========================

@router.message(F.text == "Система")
async def system_menu(message: Message):
    if not is_allowed(message.from_user.id):
        return

    if not is_session_active(message.from_user.id):
        await message.answer("⛔ Сесія не активна. Натисни «Старт»")
        return

    await message.answer(
        "⚙️ **Керування системою**",
        reply_markup=system_menu_kb,
        parse_mode="Markdown"
    )

# =========================
# SYSTEM ACTION SELECTED
# =========================

@router.callback_query(F.data.startswith("system_"))
async def system_action_selected(call: CallbackQuery):
    if not is_allowed(call.from_user.id):
        return await call.answer("⛔ Доступ заборонено", show_alert=True)

    action = call.data.replace("system_", "")

    if action == "back":
        await call.message.delete()
        return await call.answer()

    await call.message.edit_text(
        f"⏳ Коли виконати **{action}**?",
        reply_markup=delay_keyboard(action),
        parse_mode="Markdown"
    )
    await call.answer()

# =========================
# DELAY HANDLER
# =========================

@router.callback_query(F.data.startswith("delay_"))
async def delay_handler(call: CallbackQuery):
    user_id = call.from_user.id

    if call.data == "delay_cancel":
        if cancel_scheduled_action(user_id):
            await call.message.edit_text("❌ Таймер скасовано")
        else:
            await call.message.edit_text("ℹ️ Активних таймерів немає")
        return await call.answer()

    _, action, delay = call.data.split("_")
    delay = int(delay)

    await schedule_action(user_id, action, delay)

    await call.message.edit_text(
        f"✅ **{action}** буде виконано через **{delay // 60} хв**",
        parse_mode="Markdown"
    )
    await call.answer()
