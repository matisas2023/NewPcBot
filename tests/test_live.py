import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from agent.media_capture import CaptureError, CaptureService
from pc_remote.live import LiveService, recording_input
from pc_remote.runtime import write_state


class FakeProducer:
    count=0
    def __init__(self,source,camera,capture,root):
        type(self).count+=1
        self.id=f'{self.count:032x}';self.folder=Path(root)/self.id;self.folder.mkdir(parents=True)
        (self.folder/'index.m3u8').write_text('#EXTM3U\nseg00000000.ts\n')
        (self.folder/'seg00000000.ts').write_bytes(b'fixture')
        self.ready=threading.Event();self.error=None;self.stop=Mock();self.pinned=Mock(return_value=False)
    def start(self):self.ready.set()


@pytest.fixture
def live(tmp_path):
    manager=LiveService(tmp_path,SimpleNamespace(device=Mock()),FakeProducer)
    yield manager
    manager.shutdown()


def test_viewers_share_producer_and_stop_independently(live):
    one=live.start('camera',0,'session-a');two=live.start('camera',0,'session-b')
    assert one['stream']==two['stream'] and one['id']!=two['id']
    producer=next(iter(live.producers.values()))
    live.stop(one['id'],'session-a');live.sweep();producer.stop.assert_not_called()
    live.stop(two['id'],'session-b');live.sweep();producer.stop.assert_called_once()


def test_stream_files_require_matching_active_session(live):
    view=live.start('screen',0,'session-a')
    assert live.file(view['stream'],'seg00000000.ts','session-a').read_bytes()==b'fixture'
    for identity,name,owner in [(view['stream'],'seg00000000.ts','session-b'),
                                (view['stream'],'../state.json','session-a'),
                                ('../secret','index.m3u8','session-a')]:
        with pytest.raises(CaptureError):live.file(identity,name,owner)


def test_abandoned_viewer_expires_and_releases_camera(live):
    view=live.start('camera',0,'session-a');producer=next(iter(live.producers.values()))
    live.viewers[view['id']]['expires']=time.monotonic()-1
    live.sweep();producer.stop.assert_called_once()
    with pytest.raises(CaptureError):live.heartbeat(view['id'],'session-a')


def test_active_recording_keeps_producer_after_viewer_closes(live):
    view=live.start('screen',0,'session-a');producer=next(iter(live.producers.values()))
    producer.pinned.return_value=True
    live.stop(view['id'],'session-a');live.sweep();producer.stop.assert_not_called()
    producer.pinned.return_value=False;live.sweep();producer.stop.assert_called_once()


def test_recording_reuses_live_h264_and_creates_bounded_pin(tmp_path):
    root=tmp_path/'streams';folder=root/('a'*32);folder.mkdir(parents=True)
    write_state(folder/'state.json',{'state':'running','pid':os.getpid(),
        'process_created':psutil.Process().create_time(),'source':'camera','camera':0})
    (folder/'index.m3u8').write_text('#EXTM3U')
    manifest,pin=recording_input('camera',0,'b'*32,30,root)
    assert manifest==str(folder/'index.m3u8') and Path(pin).exists()
    service=CaptureService(tmp_path/'media',root)
    command=service.command({'id':'b'*32,'source':'camera','seconds':30,'live_manifest':manifest},None,None)
    assert 'copy' in command and 'dshow' not in command and 'rawvideo' not in command
    assert recording_input('camera',1,'c'*32,30,root)==(None,None)
