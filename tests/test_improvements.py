import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import tempfile
import threading

from pc_remote.runtime import InstanceLock, read_state, write_state
from pc_remote.tunnel import TunnelManager
from pc_remote.desktop import Child, startup_command


def test_second_instance_is_rejected_and_lock_released(tmp_path):
    path=tmp_path/'lock'
    with InstanceLock(path):
        try:
            with InstanceLock(path):
                raise AssertionError('Second instance acquired lock')
        except RuntimeError:
            pass
    with InstanceLock(path):
        pass


def test_atomic_state_file(tmp_path):
    path=tmp_path/'state.json'
    write_state(path,{'state':'retrying'})
    assert read_state(path)=={'state':'retrying'}
    assert list(tmp_path.glob('*.tmp'))==[]


def test_startup_has_absolute_launcher_and_no_password():
    command=startup_command(public=True)
    assert 'tray_launcher.py' in command and '--public' in command
    assert 'password' not in command and '.pc-remote.json' not in command


def test_child_shutdown_requests_graceful_stop(tmp_path):
    child=Child('agent',['pc_remote'],Mock())
    child.process=Mock()
    child.process.poll.return_value=None
    child.stop_file=tmp_path/'stop'
    child.process.wait.side_effect=lambda **kwargs: (child.stop_file.exists() or (_ for _ in ()).throw(AssertionError('No stop request')))
    process=child.process
    child.stop()
    process.wait.assert_called_once()
    process.terminate.assert_not_called()
    assert not child.stop_file.exists()


def test_failed_tunnel_does_not_stop_agent():
    server=SimpleNamespace(public_origin=None)
    failed=Mock()
    failed.start.side_effect=RuntimeError('network unavailable')
    manager=TunnelManager(server,factory=lambda _:failed)
    manager.stop_event=Mock()
    manager.stop_event.is_set.side_effect=[False,False]
    manager.stop_event.wait.return_value=True
    manager.run()
    failed.close.assert_called_once()
    assert manager.snapshot()['state']=='stopped'
    assert server.public_origin is None


def test_tunnel_reconnects_after_failure():
    server=SimpleNamespace(public_origin=None)
    attempts=[]
    manager=None
    class Failed:
        def start(self):
            attempts.append('failed')
            raise RuntimeError('offline')
        def close(self): pass
    class Online:
        process=SimpleNamespace(poll=lambda:None)
        def start(self):
            attempts.append('online')
            manager.stop_event.set()
            return 'https://test.trycloudflare.com'
        def close(self): pass
    manager=TunnelManager(server,factory=lambda _:Failed() if not attempts else Online())
    original_wait=manager.stop_event.wait
    manager.stop_event.wait=lambda delay: original_wait(0) if delay>=5 else original_wait(delay)
    manager.run()
    assert attempts==['failed','online']


def test_pointer_limits_and_no_real_mouse_actions():
    from agent.control import control_pointer
    backend=SimpleNamespace(moveRel=Mock(),scroll=Mock(),click=Mock(),doubleClick=Mock())
    with patch.dict('sys.modules',{'pyautogui':backend}):
        control_pointer(dx=23,dy=-11,scroll=2,button='right')
        backend.moveRel.assert_called_once_with(23,-11)
        backend.scroll.assert_called_once_with(2)
        backend.click.assert_called_once_with(button='right')
        try:
            control_pointer(dx=10000)
        except ValueError:
            pass
        else:
            raise AssertionError('Unbounded movement accepted')
        assert backend.moveRel.call_count==1


def test_trash_never_falls_back_to_unlink(tmp_path):
    from agent.files import move_to_trash
    file=tmp_path/'keep.txt'
    file.write_text('keep')
    backend=SimpleNamespace(send2trash=Mock(side_effect=OSError('trash unavailable')))
    with patch.dict('sys.modules',{'send2trash':backend}):
        try:
            move_to_trash(file)
        except OSError:
            pass
    assert file.read_text()=='keep'


def test_navigation_dispatch_and_confirm_callbacks(monkeypatch,allow_all):
    from aiogram import Bot, Dispatcher
    from aiogram.client.session.base import BaseSession
    from aiogram.types import Update, Message, User, Chat, CallbackQuery
    from bot.handlers import navigation, media, filesystem, system, ux
    calls=[]
    class Session(BaseSession):
        async def close(self): pass
        async def make_request(self,bot,method,timeout=None):
            calls.append(method)
            return Message(message_id=50,date=datetime.now(timezone.utc),chat=Chat(id=1,type='private'),text='reply')
        async def stream_content(self,*args,**kwargs):
            yield b''
    monkeypatch.setattr(navigation,'is_allowed',lambda _:True)
    monkeypatch.setattr(navigation,'is_session_active',lambda _:True)
    delete=Mock()
    monkeypatch.setattr(filesystem,'move_to_trash',delete)
    execute=Mock()
    monkeypatch.setattr(system,'execute_system_action',execute)
    async def run():
        bot=Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi',session=Session())
        dp=Dispatcher()
        dp.message.outer_middleware(navigation.NavigationMiddleware())
        for module in (navigation,media,filesystem,system,ux):
            dp.include_router(module.router)
        state=dp.fsm.get_context(bot=bot,chat_id=1,user_id=1)
        user=User(id=1,is_bot=False,first_name='Test')
        def message(text):
            return Message(message_id=1,date=datetime.now(timezone.utc),chat=Chat(id=1,type='private'),from_user=user,text=text)
        await state.set_state(media.MediaRecordStates.screen_seconds)
        filesystem.pending_action[1]='delete'
        filesystem.pending_delete_path[1]='dummy.txt'
        await dp.feed_update(bot,Update(update_id=1,message=message('/cancel')))
        assert await state.get_state() is None
        assert 1 not in filesystem.pending_action
        assert any('Головне меню' in getattr(call,'text','') for call in calls)
        # A menu must escape an existing media FSM instead of being parsed as seconds.
        await state.set_state(media.MediaRecordStates.audio_seconds)
        await dp.feed_update(bot,Update(update_id=2,message=message('FAQ')))
        assert any('Часті питання' in getattr(call,'text','') for call in calls)
        filesystem.pending_delete_path[1]='dummy.txt'
        await dp.feed_update(bot,Update(update_id=3,callback_query=CallbackQuery(id='fs',from_user=user,chat_instance='1',data='fs_delete_confirm',message=message('confirm'))))
        delete.assert_called_once_with('dummy.txt')
        system.pending_action[1]='Lock'
        await dp.feed_update(bot,Update(update_id=4,callback_query=CallbackQuery(id='sys',from_user=user,chat_instance='1',data='sys_confirm',message=message('confirm'))))
        execute.assert_called_once_with('Lock')
        await dp.storage.close()
        await bot.session.close()
    asyncio.run(run())
