from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

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


@dataclass
class DummyUser:
    id: int


@dataclass
class DummyChat:
    id: int


class DummyBot:
    def __init__(self) -> None:
        self.sent_messages: List[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup: Any = None) -> None:
        self.sent_messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )


class DummyMessage:
    def __init__(self, text: str | None = None, user_id: int = 1, bot: DummyBot | None = None):
        self.text = text
        self.from_user = DummyUser(user_id)
        self.chat = DummyChat(user_id)
        self.bot = bot or DummyBot()
        self.answers: List[dict[str, Any]] = []
        self.photos: List[dict[str, Any]] = []
        self.edits: List[dict[str, Any]] = []

    async def answer(self, text: str, reply_markup: Any = None) -> None:
        self.answers.append({"text": text, "reply_markup": reply_markup})

    async def answer_photo(self, photo: Any = None, caption: str | None = None, reply_markup: Any = None) -> None:
        self.photos.append({"photo": photo, "caption": caption, "reply_markup": reply_markup})

    async def edit_text(self, text: str, reply_markup: Any = None) -> None:
        self.edits.append({"text": text, "reply_markup": reply_markup})

    async def edit_media(self, media: Any = None, reply_markup: Any = None) -> None:
        self.edits.append({"media": media, "reply_markup": reply_markup})


class DummyCallbackQuery:
    def __init__(
        self,
        data: str,
        message: DummyMessage,
        user_id: int = 1,
        bot: DummyBot | None = None,
    ) -> None:
        self.data = data
        self.from_user = DummyUser(user_id)
        self.message = message
        self.bot = bot or message.bot
        self.answers: List[dict[str, Any]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})


class DummyFSMContext:
    def __init__(self) -> None:
        self.state: str | None = None

    async def set_state(self, state: Any) -> None:
        self.state = str(state)

    async def clear(self) -> None:
        self.state = None


@pytest.fixture()
def allow_all(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    modules = [
        start,
        status,
        screenshot,
        system,
        media,
        media_controls,
        processes,
        filesystem,
        autoreport,
        ux,
    ]

    for module in modules:
        if hasattr(module, "is_allowed"):
            monkeypatch.setattr(module, "is_allowed", lambda *_: True)
        if hasattr(module, "is_session_active"):
            monkeypatch.setattr(module, "is_session_active", lambda *_: True)
        if hasattr(module, "log_action"):
            monkeypatch.setattr(module, "log_action", lambda *args, **kwargs: None)

    monkeypatch.setattr(start, "start_session", lambda *_: None)
    monkeypatch.setattr(start, "end_session", lambda *_: None)

    monkeypatch.setattr(
        status,
        "get_status",
        lambda: {
            "pc": "test-pc",
            "os": "test-os",
            "cpu": 10,
            "ram": 20,
            "disk": 30,
            "ip": "127.0.0.1",
            "uptime": 123,
        },
    )

    def fake_screenshot() -> Any:
        path = tmp_path / "screenshot.png"
        path.write_bytes(b"fake")
        return path

    monkeypatch.setattr(screenshot, "take_screenshot", fake_screenshot)
    monkeypatch.setattr(system, "execute_system_action", lambda *_: None)

    class DummyTask:
        def cancel(self) -> None:
            return None

    def fake_create_task(coro) -> DummyTask:
        coro.close()
        return DummyTask()

    monkeypatch.setattr(system.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(media.subprocess, "Popen", lambda *args, **kwargs: None)

    class DummyControls:
        def __init__(self) -> None:
            self.currentItem = object()

        def isAvailable(self, _name: str) -> bool:
            return True

        def pause(self) -> None:
            return None

        def play(self) -> None:
            return None

        def next(self) -> None:
            return None

        def previous(self) -> None:
            return None

    class DummySettings:
        def __init__(self) -> None:
            self.volume = 50
            self.mute = False

    class DummyWmp:
        def __init__(self) -> None:
            self.controls = DummyControls()
            self.settings = DummySettings()

    monkeypatch.setattr(media_controls, "get_wmp", lambda: DummyWmp())
    monkeypatch.setattr(
        media_controls,
        "get_pyautogui",
        lambda: SimpleNamespace(
            press=lambda *args, **kwargs: None,
            hotkey=lambda *args, **kwargs: None,
            click=lambda *args, **kwargs: None,
            moveRel=lambda *args, **kwargs: None,
        ),
    )

    monkeypatch.setattr(
        processes.psutil,
        "process_iter",
        lambda *args, **kwargs: iter(
            [
                SimpleNamespace(
                    info={
                        "pid": 1,
                        "name": "proc",
                        "cpu_percent": 0.1,
                        "memory_percent": 1.0,
                    }
                )
            ]
        ),
    )

    monkeypatch.setattr(filesystem.os, "listdir", lambda *_: [])
    monkeypatch.setattr(filesystem.os.path, "isfile", lambda *_: False)
    monkeypatch.setattr(filesystem.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(filesystem.shutil, "copy", lambda *args, **kwargs: None)

    class DummyZip:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self) -> "DummyZip":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def write(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr(filesystem.zipfile, "ZipFile", DummyZip)
    monkeypatch.setattr(filesystem.os, "remove", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        autoreport,
        "get_status",
        lambda: {
            "pc": "test-pc",
            "cpu": 10,
            "ram": 20,
            "disk": 30,
            "uptime": 123,
        },
    )
    monkeypatch.setattr(autoreport.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(ux, "read_last_actions", lambda *args, **kwargs: ["User 1 | action"])
    monkeypatch.setattr(ux, "format_screenshot_history", lambda *_: [])

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(ux.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(ux, "speak_text", lambda *_: None)

    filesystem.pending_action.clear()
    filesystem.pending_delete_path.clear()
    system.pending_action.clear()
    system.scheduled_tasks.clear()
    autoreport.auto_report_tasks.clear()
    autoreport.threshold_states.clear()
    autoreport.pending_popup.clear()
    ux.pending_speech.clear()
    ux.theme_preferences.clear()

    yield

    filesystem.pending_action.clear()
    filesystem.pending_delete_path.clear()
    system.pending_action.clear()
    system.scheduled_tasks.clear()
    autoreport.auto_report_tasks.clear()
    autoreport.threshold_states.clear()
    autoreport.pending_popup.clear()
    ux.pending_speech.clear()
    ux.theme_preferences.clear()
