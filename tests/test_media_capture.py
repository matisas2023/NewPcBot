import asyncio
import io
import os
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import psutil
import pytest

from agent.media_capture import CaptureService, CaptureError
from pc_remote.runtime import write_state


def stored_job(service, owner='web', status='ready'):
    identity='a'*32
    job={'id':identity,'owner':owner,'source':'screen','status':status,'seconds':2,
         'created':time.time(),'pid':os.getpid(),'process_created':psutil.Process().create_time()}
    write_state(service._path(identity,'.json'),job)
    service._path(identity,'.mp4').write_bytes(b'fixture'*100)
    return identity


@pytest.mark.parametrize('source,seconds',[('unknown',10),('screen',0),('camera',121),('screen',True),('audio','10')])
def test_capture_rejects_invalid_request_before_launch(tmp_path,source,seconds):
    service=CaptureService(tmp_path)
    with patch('agent.media_capture.subprocess.Popen') as launch:
        with pytest.raises(CaptureError):service.start(source,seconds,'web')
        launch.assert_not_called()


def test_owner_cannot_read_or_stop_another_users_recording(tmp_path):
    service=CaptureService(tmp_path);identity=stored_job(service,owner='tg:123',status='recording')
    for operation in (service.file,service.stop,service.delete):
        with pytest.raises(CaptureError):operation(identity,'web')
    assert not service._path(identity,'.stop').exists()
    with pytest.raises(CaptureError):service.file('../secret','web')


def test_failed_encoder_releases_source_and_reports_error(tmp_path):
    service=CaptureService(tmp_path)
    process=SimpleNamespace(stdin=io.BytesIO(),returncode=1,poll=lambda:1)
    with patch('agent.media_capture.subprocess.Popen',return_value=process),patch.object(service,'command',return_value=['fixture']):
        job=service.start('screen',1,'web')
        service.shutdown()
    assert service.get(job['id'],'web')['status']=='error'
    with service.source_lock('screen'):pass


def test_shutdown_stops_only_local_workers(tmp_path):
    service=CaptureService(tmp_path);identity=stored_job(service,status='recording')
    service.stop(identity,'web')
    assert service._path(identity,'.stop').exists()


def test_disk_error_does_not_leave_source_locked(tmp_path):
    service=CaptureService(tmp_path)
    with patch('agent.media_capture.write_state',side_effect=OSError('disk full')):
        with pytest.raises(OSError):service.start('screen',1,'web')
    with service.source_lock('screen'):pass


def test_bot_waits_for_completion_then_sends_video(tmp_path,monkeypatch):
    from bot.handlers import media
    path=tmp_path/'clip.mp4';path.write_bytes(b'fixture')
    capture=SimpleNamespace(start=Mock(return_value={'id':'a'*32,'status':'recording'}),
        get=Mock(return_value={'id':'a'*32,'status':'ready'}),file=Mock(return_value=path),stop=Mock())
    monkeypatch.setattr(media,'service',capture)
    monkeypatch.setattr(media,'allowed',lambda user:True)
    monkeypatch.setattr(media,'log_action',lambda *args:None)
    monkeypatch.setattr(media.asyncio,'sleep',AsyncMock())
    message=SimpleNamespace(from_user=SimpleNamespace(id=7),text='2',answer=AsyncMock(),answer_video=AsyncMock())
    state=SimpleNamespace(get_data=AsyncMock(return_value={}),clear=AsyncMock())
    asyncio.run(media.record_screen(message,state))
    message.answer_video.assert_awaited_once()
    assert message.answer_video.call_args.kwargs['video'].path==path
    assert message.answer_video.call_args.kwargs['supports_streaming'] is True
    capture.get.assert_called_with('a'*32,'tg:7')


def test_bot_rechecks_authorization_before_recording(monkeypatch):
    from bot.handlers import media
    monkeypatch.setattr(media,'allowed',lambda user:False)
    capture=Mock();monkeypatch.setattr(media,'service',capture)
    message=SimpleNamespace(from_user=SimpleNamespace(id=7),text='30',answer=AsyncMock())
    asyncio.run(media.record_camera(message,Mock()))
    capture.start.assert_not_called()
    message.answer.assert_awaited_once()
