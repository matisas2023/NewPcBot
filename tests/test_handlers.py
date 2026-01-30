from __future__ import annotations

from typing import Any, Iterable, List

import asyncio

from bot.handlers import (
    autoreport,
    filesystem,
    media,
    media_controls,
    processes,
    screenshot,
    start,
    status,
    system,
    ux,
)
from bot.keyboards import main_menu, screenshot_kb

from tests.conftest import DummyCallbackQuery, DummyFSMContext, DummyMessage


def _extract_reply_buttons(markup) -> List[str]:
    return [button.text for row in markup.keyboard for button in row]


def _extract_callbacks(markup) -> List[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _assert_message_responded(message: DummyMessage) -> None:
    assert message.answers or message.photos or message.edits


def _assert_call_responded(call: DummyCallbackQuery) -> None:
    assert call.answers or call.message.answers or call.message.edits or call.message.photos or call.bot.sent_messages


def test_menu_buttons_have_handlers_and_respond(allow_all) -> None:
    async def run() -> None:
        mapping = {
            "Старт": start.start_handler,
            "Статус ПК": status.status_pc,
            "Скриншот": screenshot.screenshot_handler,
            "Система": system.system_menu,
            "Медіа": media.media_menu,
            "Процеси": processes.list_processes,
            "Файлова система": filesystem.fs_menu,
            "Медіаплеєр": media_controls.media_controls_menu,
            "Введення": media_controls.input_controls_menu,
            "Автозвіти": autoreport.autoreport_menu,
            "Історія": ux.history_menu,
            "FAQ": ux.faq_menu,
            "Тема": ux.toggle_theme,
            "Голос": ux.speech_prompt,
            "Досягнення": ux.achievements,
            "Вихід": start.logout_handler,
        }

        for button_text in _extract_reply_buttons(main_menu):
            handler = mapping.get(button_text)
            assert handler is not None, f"Missing handler for button: {button_text}"
            message = DummyMessage(text=button_text)
            await handler(message)
            _assert_message_responded(message)

    asyncio.run(run())


def test_inline_callbacks_have_handlers_and_respond(allow_all) -> None:
    async def run() -> None:
        def make_call(data: str) -> DummyCallbackQuery:
            return DummyCallbackQuery(data=data, message=DummyMessage())

        async def run_handler(handler, data: str, *, state: DummyFSMContext | None = None, setup=None) -> None:
            if setup:
                setup()
            call = make_call(data)
            if state is None:
                await handler(call)
            else:
                await handler(call, state)
            _assert_call_responded(call)

        async def run_media_select(data: str) -> None:
            await run_handler(media.media_select, data, state=DummyFSMContext())

        await run_handler(screenshot.screenshot_refresh, "screenshot_refresh")

        await run_handler(system.system_select, "sys_Shutdown")
        await run_handler(system.system_select, "sys_Restart")
        await run_handler(system.system_select, "sys_Lock")
        await run_handler(system.system_select, "sys_Logoff")
        await run_handler(system.system_select, "sys_Sleep")
        await run_handler(system.system_select, "sys_Hibernate")
        await run_handler(system.system_select, "sys_timer_10")
        await run_handler(system.system_select, "sys_timer_30")

        await run_handler(
            system.system_execute,
            "sys_confirm",
            setup=lambda: system.pending_action.update({1: "Shutdown"}),
        )
        await run_handler(
            system.system_execute,
            "sys_cancel",
            setup=lambda: system.pending_action.update({1: "Shutdown"}),
        )

        await run_media_select("media_screen")
        await run_media_select("media_camera")
        await run_media_select("media_audio")

        for data in [
            "mediaplayer_playpause",
            "mediaplayer_next",
            "mediaplayer_prev",
            "mediaplayer_volup",
            "mediaplayer_voldown",
            "mediaplayer_mute",
        ]:
            await run_handler(media_controls.media_controls_action, data)

        for data in [
            "input_esc",
            "input_enter",
            "input_alttab",
            "input_click",
            "input_move_up",
            "input_move_down",
            "input_move_left",
            "input_move_right",
        ]:
            await run_handler(media_controls.input_controls_action, data)

        for data in ["fs_list", "fs_upload", "fs_delete", "fs_search", "fs_archive", "fs_backup"]:
            await run_handler(filesystem.fs_actions, data)

        await run_handler(
            filesystem.fs_delete_confirm,
            "fs_delete_confirm",
            setup=lambda: filesystem.pending_delete_path.update({1: "dummy.txt"}),
        )
        await run_handler(
            filesystem.fs_delete_confirm,
            "fs_delete_cancel",
            setup=lambda: filesystem.pending_delete_path.update({1: "dummy.txt"}),
        )

        for data in [
            "autoreport_start",
            "autoreport_stop",
            "autoreport_send",
            "autoreport_popup",
        ]:
            await run_handler(autoreport.autoreport_actions, data)

        for data in ["faq_start", "faq_screenshot", "faq_files", "faq_autoreport"]:
            await run_handler(ux.faq_answer, data)

    asyncio.run(run())


def _all_callbacks_from_keyboards() -> Iterable[str]:
    callbacks: List[str] = []
    callbacks.extend(_extract_callbacks(screenshot_kb))
    callbacks.extend(_extract_callbacks(filesystem.filesystem_menu_kb()))
    callbacks.extend(_extract_callbacks(system.system_menu_kb()))
    callbacks.extend(_extract_callbacks(system.system_confirm_kb()))
    callbacks.extend(_extract_callbacks(media.media_menu_kb()))
    callbacks.extend(_extract_callbacks(media_controls.media_controls_kb()))
    callbacks.extend(_extract_callbacks(media_controls.input_controls_kb()))
    callbacks.extend(_extract_callbacks(autoreport.autoreport_keyboard()))
    callbacks.extend(_extract_callbacks(ux.faq_keyboard()))
    return callbacks


def test_callback_coverage_matches_handlers() -> None:
    handler_callbacks = {
        "screenshot_refresh",
        "sys_Shutdown",
        "sys_Restart",
        "sys_Lock",
        "sys_Logoff",
        "sys_Sleep",
        "sys_Hibernate",
        "sys_timer_10",
        "sys_timer_30",
        "sys_confirm",
        "sys_cancel",
        "media_screen",
        "media_camera",
        "media_audio",
        "mediaplayer_playpause",
        "mediaplayer_next",
        "mediaplayer_prev",
        "mediaplayer_volup",
        "mediaplayer_voldown",
        "mediaplayer_mute",
        "input_esc",
        "input_enter",
        "input_alttab",
        "input_click",
        "input_move_up",
        "input_move_down",
        "input_move_left",
        "input_move_right",
        "fs_list",
        "fs_upload",
        "fs_delete",
        "fs_search",
        "fs_archive",
        "fs_backup",
        "fs_delete_confirm",
        "fs_delete_cancel",
        "autoreport_start",
        "autoreport_stop",
        "autoreport_send",
        "autoreport_popup",
        "faq_start",
        "faq_screenshot",
        "faq_files",
        "faq_autoreport",
    }
    missing = [cb for cb in _all_callbacks_from_keyboards() if cb not in handler_callbacks]
    assert not missing, f"Missing handlers for callbacks: {missing}"


def test_menu_button_coverage_matches_handlers() -> None:
    handler_buttons = {
        "Старт",
        "Статус ПК",
        "Скриншот",
        "Система",
        "Медіа",
        "Процеси",
        "Файлова система",
        "Медіаплеєр",
        "Введення",
        "Автозвіти",
        "Історія",
        "FAQ",
        "Тема",
        "Голос",
        "Досягнення",
        "Вихід",
    }
    menu_buttons = set(_extract_reply_buttons(main_menu))
    assert menu_buttons == handler_buttons


def test_fallback_allowed_commands_cover_main_menu() -> None:
    from bot.handlers import fallback

    menu_buttons = set(_extract_reply_buttons(main_menu))
    assert menu_buttons.issubset(fallback._ALLOWED_COMMANDS)


def test_security_allowed_status_handler(allow_all) -> None:
    async def run() -> None:
        message = DummyMessage(text="Статус ПК")
        await status.status_pc(message)
        assert message.answers
        assert "🖥" in message.answers[0]["text"]

    asyncio.run(run())


def test_security_denied_status_handler(monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(status, "is_allowed", lambda *_: False)
        message = DummyMessage(text="Статус ПК")
        await status.status_pc(message)
        assert message.answers
        assert message.answers[0]["text"] == "⛔ Доступ заборонено"

    asyncio.run(run())
