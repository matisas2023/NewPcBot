"""Authenticated HLS producers shared by viewers and bounded recordings."""
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from .runtime import STATE_DIR, read_state, write_state

LIVE_DIR = STATE_DIR/'live'
LEASE_SECONDS = 35


def active_state(folder):
    import psutil
    state=read_state(folder/'state.json')
    if not isinstance(state,dict) or state.get('state')!='running':return None
    try:
        if abs(psutil.Process(state['pid']).create_time()-state['process_created'])>0.1:return None
    except (psutil.Error,KeyError,TypeError):return None
    return state


def recording_input(source, camera, identity, seconds, root=LIVE_DIR):
    """Pin an existing encoder; recording must not reopen the physical camera."""
    for folder in Path(root).glob('*'):
        if not re.fullmatch(r'[a-f0-9]{32}',folder.name):continue
        state=active_state(folder)
        if not state or state.get('source')!=source or source=='camera' and state.get('camera')!=camera:continue
        manifest=folder/'index.m3u8'
        if not manifest.exists():continue
        pin=folder/(identity+'.pin')
        write_state(pin,{'expires':time.time()+seconds+30})
        return str(manifest),str(pin)
    return None,None


def camera_frame(camera, root=LIVE_DIR):
    for folder in Path(root).glob('*'):
        state=active_state(folder)
        if state and state.get('source')=='camera' and state.get('camera')==camera:
            path=folder/'latest.jpg'
            try:
                if time.time()-path.stat().st_mtime<5:return path.read_bytes()
            except OSError:pass
    return None


class Producer:
    def __init__(self, source, camera, capture, root):
        self.id=uuid.uuid4().hex
        self.source,self.camera,self.capture=source,camera,capture
        self.folder=Path(root)/self.id
        self.folder.mkdir(parents=True,exist_ok=True)
        self.done=threading.Event();self.ready=threading.Event()
        self.error=None;self.process=None;self.thread=None
        self.hold=capture.source_lock(source)
        self.hold.__enter__()

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def pinned(self):
        for path in self.folder.glob('*.pin'):
            state=read_state(path)
            if isinstance(state,dict) and state.get('expires',0)>time.time():return True
            path.unlink(missing_ok=True)
        return False

    def output_args(self):
        return ['-an','-vf',"scale=w='min(1280,iw)':h=-2",'-r','15','-c:v','libx264',
            '-preset','ultrafast','-tune','zerolatency','-pix_fmt','yuv420p','-profile:v','baseline',
            '-crf','27','-maxrate','1800k','-bufsize','1800k','-g','15','-keyint_min','15','-sc_threshold','0',
            '-f','hls','-hls_time','1','-hls_list_size','6','-hls_delete_threshold','10',
            '-hls_flags','delete_segments+independent_segments+temp_file',
            '-hls_segment_filename',str(self.folder/'seg%08d.ts'),str(self.folder/'index.m3u8')]

    def run(self):
        from agent.media_capture import executable, FLAGS
        import psutil
        camera=None
        try:
            args=[executable(),'-hide_banner','-loglevel','error','-y']
            first=None
            if self.source=='camera':
                import cv2
                camera=cv2.VideoCapture(self.camera,cv2.CAP_DSHOW)
                ok,first=camera.read() if camera.isOpened() else (False,None)
                if not ok:raise RuntimeError('Камера недоступна. Закрий іншу програму або перевір доступ Windows.')
                h,w=first.shape[:2]
                args+=['-f','rawvideo','-pix_fmt','bgr24','-video_size',f'{w}x{h}','-framerate','15','-i','pipe:0']
            else:args+=['-f','gdigrab','-framerate','15','-i','desktop']
            with (self.folder/'encoder.log').open('wb') as log:
                self.process=subprocess.Popen(args+self.output_args(),stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,stderr=log,creationflags=FLAGS)
                write_state(self.folder/'state.json',{'state':'running','source':self.source,'camera':self.camera,
                    'pid':os.getpid(),'process_created':psutil.Process().create_time()})
                next_frame=time.monotonic();last_preview=0;frame=first
                while not self.done.is_set() and self.process.poll() is None:
                    if camera:
                        try:self.process.stdin.write(frame.tobytes())
                        except BrokenPipeError:break
                        if time.monotonic()-last_preview>0.5:
                            ok,jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,70])
                            if ok:
                                temporary=self.folder/'latest.frame';temporary.write_bytes(jpeg.tobytes());os.replace(temporary,self.folder/'latest.jpg')
                            last_preview=time.monotonic()
                    if (self.folder/'index.m3u8').exists():self.ready.set()
                    if camera:
                        next_frame+=1/15;self.done.wait(max(0,next_frame-time.monotonic()))
                        ok,frame=camera.read()
                        if not ok:raise RuntimeError('Камера перестала віддавати кадри')
                    else:self.done.wait(0.1)
                if not self.done.is_set():raise RuntimeError('Відеотрансляція перервалася. Перевір джерело й запусти знову.')
        except Exception as exc:
            self.error=str(exc) if isinstance(exc,RuntimeError) else 'Не вдалося запустити відеотрансляцію'
        finally:
            if camera:camera.release()
            if self.process:
                if self.process.poll() is None:
                    try:
                        if self.source=='camera':self.process.stdin.close()
                        else:self.process.stdin.write(b'q\n');self.process.stdin.flush()
                        self.process.wait(timeout=5)
                    except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=5)
                try:self.process.stdin.close()
                except OSError:pass
            try:write_state(self.folder/'state.json',{'state':'stopped'})
            finally:self.hold.__exit__(None,None,None)
            self.ready.set()
            for file in self.folder.iterdir():
                if file.suffix in ('.ts','.m3u8','.tmp','.jpg','.frame'):
                    try:file.unlink()
                    except OSError:pass

    def stop(self):
        self.done.set()
        if self.thread:self.thread.join(timeout=10)


class LiveService:
    def __init__(self, root=LIVE_DIR, capture=None, factory=Producer):
        self.root=Path(root);self.capture=capture;self.factory=factory
        self.lock=threading.RLock();self.producers={};self.viewers={}
        self.done=threading.Event();self.monitor=None

    def start(self, source, camera, owner):
        from agent.media_capture import service, CaptureError
        capture=self.capture or service
        if source not in ('screen','camera') or type(camera) is not int or camera<0:
            raise CaptureError('Обери камеру або екран')
        if source=='camera':capture.device('cameras',camera)
        with self.lock:
            if len(self.viewers)>=8:raise CaptureError('Забагато переглядів. Закрий непотрібні вкладки.')
            key=(source,camera if source=='camera' else 0)
            producer=self.producers.get(key)
            if not producer:
                try:producer=self.factory(source,camera,capture,self.root)
                except RuntimeError as exc:raise CaptureError('Джерело зайняте іншим записом. Зупини його та спробуй знову.') from exc
                self.producers[key]=producer;producer.start()
            identity=uuid.uuid4().hex
            self.viewers[identity]={'producer':producer,'owner':owner,'expires':time.monotonic()+LEASE_SECONDS}
            if not self.monitor:
                self.monitor=threading.Thread(target=self.watch,daemon=True);self.monitor.start()
        if not producer.ready.wait(12) or producer.error:
            self.stop(identity,owner)
            raise CaptureError(producer.error or 'Відео ще не готове. Спробуй запустити трансляцію знову.')
        return {'id':identity,'stream':producer.id,'url':f'/api/media/live/{producer.id}/index.m3u8',
                'fps':15,'lease_seconds':LEASE_SECONDS}

    def heartbeat(self, identity, owner):
        from agent.media_capture import CaptureError
        with self.lock:
            viewer=self.viewers.get(identity)
            if not viewer or viewer['owner']!=owner or viewer['expires']<time.monotonic():
                raise CaptureError('Трансляцію завершено. Натисни «Трансляція» ще раз.')
            if viewer['producer'].error:raise CaptureError(viewer['producer'].error)
            viewer['expires']=time.monotonic()+LEASE_SECONDS

    def stop(self, identity, owner):
        with self.lock:
            viewer=self.viewers.get(identity)
            if viewer and viewer['owner']==owner:self.viewers.pop(identity,None)

    def file(self, identity, name, owner):
        from agent.media_capture import CaptureError
        if not re.fullmatch(r'[a-f0-9]{32}',identity) or not re.fullmatch(r'index\.m3u8|seg\d{8}\.ts',name):
            raise CaptureError('Невідомий файл трансляції')
        with self.lock:
            if not any(v['owner']==owner and v['producer'].id==identity and v['expires']>time.monotonic() for v in self.viewers.values()):
                raise CaptureError('Трансляція недоступна для цього сеансу')
        path=self.root/identity/name
        if not path.is_file():raise CaptureError('Фрагмент відео вже недоступний. Перезапусти трансляцію.')
        return path

    def sweep(self):
        retired=[]
        with self.lock:
            self.viewers={key:v for key,v in self.viewers.items() if v['expires']>time.monotonic() and not v['producer'].error}
            used={v['producer'] for v in self.viewers.values()}
            for key,producer in list(self.producers.items()):
                if producer not in used and not producer.pinned():
                    self.producers.pop(key);retired.append(producer)
        for producer in retired:producer.stop()

    def watch(self):
        while not self.done.wait(2):self.sweep()

    def shutdown(self):
        self.done.set()
        with self.lock:producers=list(self.producers.values());self.viewers.clear();self.producers.clear()
        for producer in producers:producer.stop()
        if self.monitor:self.monitor.join(timeout=3)


live=LiveService()
