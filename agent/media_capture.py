"""Bounded, explicit PC capture shared by the web panel and Telegram."""
import io
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from pc_remote.runtime import STATE_DIR, InstanceLock, read_state, write_state

DIRECTORY = STATE_DIR/'media'
MAX_FILE = 25*1024*1024
MAX_STORAGE = 500*1024*1024
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


class CaptureError(RuntimeError):
    pass


def executable():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class CaptureService:
    def __init__(self, directory=DIRECTORY, live_directory=None):
        self.directory = Path(directory)
        self.live_directory = Path(live_directory) if live_directory else (STATE_DIR/'live' if self.directory==DIRECTORY else self.directory/'live')
        self.lock = threading.RLock()
        self.workers = {}
        self.device_cache = None
        self.device_time = 0

    def devices(self):
        with self.lock:
            if self.device_cache is not None and time.monotonic()-self.device_time < 30:
                return self.device_cache
            try:
                result = subprocess.run([executable(),'-hide_banner','-list_devices','true','-f','dshow','-i','dummy'],
                    capture_output=True,timeout=12,creationflags=FLAGS)
            except (OSError,subprocess.TimeoutExpired) as exc:
                raise CaptureError('Не вдалося знайти пристрої захоплення. Перевір FFmpeg і підключення камери.') from exc
            devices = {'cameras':[], 'microphones':[]}
            for name,kind in re.findall(r'"([^"\r\n]+)" \((video|audio|none)\)',result.stderr.decode('utf-8',errors='replace')):
                group = devices['cameras' if kind!='audio' else 'microphones']
                if name not in [item['name'] for item in group]:
                    group.append({'id':len(group),'name':name})
            self.device_cache,self.device_time = devices,time.monotonic()
            return devices

    def device(self, group, index):
        if type(index) is not int or index < 0:
            raise CaptureError('Некоректний номер пристрою')
        devices = self.devices()[group]
        if index >= len(devices):
            raise CaptureError('Камеру не знайдено або вона відключена' if group=='cameras' else 'Мікрофон не знайдено')
        return devices[index]['name']

    def source_lock(self, source):
        return InstanceLock(self.directory/f'{source}.lock')

    def snapshot(self, source, camera=0):
        if source not in ('screen','camera'):
            raise CaptureError('Невідоме джерело')
        if source=='screen':
            from agent.control import capture_screen
            from PIL import Image
            image=Image.open(io.BytesIO(capture_screen()))
            image.thumbnail((1280,720))
            result=io.BytesIO();image.convert('RGB').save(result,format='JPEG',quality=65)
            return result.getvalue()
        self.device('cameras',camera)
        from pc_remote.live import camera_frame
        frame=camera_frame(camera,self.live_directory)
        if frame:return frame
        # A recording supplies preview frames without opening the camera a second time.
        for job in self.list_jobs(None):
            frame=self.directory/f'{job["id"]}.jpg'
            if job['source']==source and job.get('camera')==camera and job['status']=='recording':
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    try:
                        if time.time()-frame.stat().st_mtime < 5:return frame.read_bytes()
                    except OSError:pass
                    time.sleep(0.1)
                raise CaptureError('Камера готує кадр запису. Спробуй ще раз за секунду.')
        try:
            with self.source_lock('camera'):
                import cv2
                capture=cv2.VideoCapture(camera,cv2.CAP_DSHOW)
                try:
                    ok,frame=capture.read() if capture.isOpened() else (False,None)
                    if not ok:raise CaptureError('Камера недоступна: закрий іншу програму або перевір доступ Windows.')
                    height,width=frame.shape[:2]
                    frame=cv2.resize(frame,(640,max(2,round(height*640/width))))
                    ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,65])
                    if not ok:raise CaptureError('Не вдалося отримати кадр камери')
                    return encoded.tobytes()
                finally:capture.release()
        except RuntimeError as exc:
            if isinstance(exc,CaptureError): raise
            raise CaptureError('Камера зайнята іншим записом. Зупини його та спробуй знову.') from exc

    def _path(self, identity, suffix):
        if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{32}',identity):
            raise CaptureError('Некоректний ідентифікатор запису')
        return self.directory/(identity+suffix)

    def get(self, identity, owner):
        job=read_state(self._path(identity,'.json'))
        if not isinstance(job,dict) or not job or owner is not None and job.get('owner')!=owner:
            raise CaptureError('Запис не знайдено')
        if job.get('status')=='recording':
            import psutil
            try:
                alive=abs(psutil.Process(job['pid']).create_time()-job['process_created']) < 0.1
            except (psutil.Error,KeyError):
                alive=False
            if not alive:
                job['status']='error';job['error']='Запис перервано перезапуском агента'
        file=self._path(identity,'.mp3' if job['source']=='audio' else '.mp4')
        job['size']=file.stat().st_size if file.exists() else 0
        return job

    def list_jobs(self, owner):
        if not self.directory.exists(): return []
        result=[]
        for path in self.directory.glob('*.json'):
            try:
                result.append(self.get(path.stem,owner))
            except (CaptureError,OSError): pass
        return sorted(result,key=lambda job:job['created'],reverse=True)[:100]

    def start(self, source, seconds, owner, camera=0, microphone=None):
        if source not in ('screen','camera','audio') or type(seconds) is not int or not 1<=seconds<=120:
            raise CaptureError('Обери джерело та тривалість від 1 до 120 секунд')
        self.directory.mkdir(parents=True,exist_ok=True)
        if sum(path.stat().st_size for path in self.directory.iterdir() if path.is_file())>=MAX_STORAGE:
            raise CaptureError('Сховище записів заповнене (500 МБ). Видали непотрібні записи.')
        camera_name=self.device('cameras',camera) if source=='camera' else None
        microphone_name=self.device('microphones',0 if microphone is None else microphone) if source=='audio' or microphone is not None else None
        identity=uuid.uuid4().hex
        from pc_remote.live import recording_input
        manifest,pin=recording_input(source,camera,identity,seconds,self.live_directory) if source!='audio' else (None,None)
        locks=[]
        try:
            for kind in sorted({'record-'+source}|(set() if manifest else {source})|({'audio'} if microphone_name else set())):
                handle=self.source_lock(kind);handle.__enter__();locks.append(handle)
        except RuntimeError as exc:
            for handle in reversed(locks):handle.__exit__(None,None,None)
            if pin:Path(pin).unlink(missing_ok=True)
            raise CaptureError('Це джерело вже використовується. Зупини попередній запис.') from exc
        import psutil
        job={'id':identity,'owner':owner,'source':source,'camera':camera,'seconds':seconds,
             'created':time.time(),'status':'recording','pid':os.getpid(),
             'process_created':psutil.Process().create_time(),'error':None,'live_manifest':manifest,'live_pin':pin}
        try:
            write_state(self._path(identity,'.json'),job)
            thread=threading.Thread(target=self._record,args=(job,camera_name,microphone_name,locks),daemon=True)
            with self.lock:self.workers[identity]=thread
            thread.start()
        except Exception:
            if pin:Path(pin).unlink(missing_ok=True)
            for handle in reversed(locks):handle.__exit__(None,None,None)
            with self.lock:self.workers.pop(identity,None)
            raise
        return job

    def command(self, job, camera_name, microphone_name):
        args=[executable(),'-hide_banner','-loglevel','error','-y']
        if job.get('live_manifest'):args+=['-live_start_index','-1','-protocol_whitelist','file,crypto,data','-i',job['live_manifest']]
        elif job['source']=='screen':args+=['-f','gdigrab','-framerate','15','-i','desktop']
        if microphone_name:args+=['-f','dshow','-i','audio='+microphone_name]
        if job['source']=='audio':
            return args+['-t',str(job['seconds']),'-c:a','libmp3lame','-b:a','128k',
                str(self._path(job['id'],'.mp3'))]
        args+=['-map','0:v:0']
        args+=['-map','1:a:0','-c:a','aac','-b:a','96k'] if microphone_name else ['-an']
        args+=['-t',str(job['seconds'])]
        if job.get('live_manifest'):args+=['-c:v','copy']
        else:args+=['-vf',"scale=w='min(1280,iw)':h=-2",'-r','15','-c:v','libx264','-preset','ultrafast','-crf','28','-maxrate','1800k','-bufsize','3600k','-pix_fmt','yuv420p']
        args+=['-movflags','+faststart','-fs',str(MAX_FILE-1024*1024),str(self._path(job['id'],'.mp4'))]
        return args

    def _camera_record(self, job, microphone_name):
        import cv2
        capture=cv2.VideoCapture(job['camera'],cv2.CAP_DSHOW)
        process=None
        try:
            ok,frame=capture.read() if capture.isOpened() else (False,None)
            if not ok:raise CaptureError('Камера не віддає кадри. Закрий іншу програму та перевір доступ Windows.')
            height,width=frame.shape[:2];width=min(1280,width)//2*2;height=max(2,round(height*width/frame.shape[1])//2*2)
            args=[executable(),'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgr24',
                  '-video_size',f'{width}x{height}','-framerate','15','-i','pipe:0']
            if microphone_name:args+=['-thread_queue_size','512','-f','dshow','-i','audio='+microphone_name]
            args+=['-map','0:v:0']
            args+=['-map','1:a:0','-c:a','aac','-b:a','96k','-shortest'] if microphone_name else ['-an']
            args+=['-t',str(job['seconds']),'-c:v','libx264','-preset','ultrafast','-crf','28',
                '-maxrate','1800k','-bufsize','3600k','-pix_fmt','yuv420p','-movflags','+faststart',
                '-fs',str(MAX_FILE-1024*1024),str(self._path(job['id'],'.mp4'))]
            with self._path(job['id'],'.log').open('wb') as log:
                process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log,creationflags=FLAGS)
                deadline=time.monotonic()+job['seconds'];next_frame=time.monotonic();last_preview=0
                while time.monotonic()<deadline and not self._path(job['id'],'.stop').exists():
                    if not ok:raise CaptureError('Зв’язок із камерою втрачено')
                    frame=cv2.resize(frame,(width,height))
                    try:process.stdin.write(frame.tobytes())
                    except BrokenPipeError:break
                    if time.monotonic()-last_preview>=0.5:
                        ok_jpeg,encoded=cv2.imencode('.jpg',cv2.resize(frame,(640,max(2,round(height*640/width)))),[cv2.IMWRITE_JPEG_QUALITY,65])
                        if ok_jpeg:
                            temporary=self._path(job['id'],'.frame');temporary.write_bytes(encoded.tobytes())
                            os.replace(temporary,self._path(job['id'],'.jpg'))
                        last_preview=time.monotonic()
                    next_frame+=1/15;time.sleep(max(0,next_frame-time.monotonic()))
                    ok,frame=capture.read()
                try:process.stdin.close()
                except OSError:pass
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                if process.returncode:raise CaptureError('Не вдалося закодувати відео камери. Спробуй без мікрофона.')
        finally:
            capture.release()
            if process and process.poll() is None:process.kill();process.wait(timeout=5)

    def _record(self, job, camera_name, microphone_name, locks):
        process=None
        try:
            if job['source']=='camera' and not job.get('live_manifest'):
                self._camera_record(job,microphone_name)
            else:
                with self._path(job['id'],'.log').open('wb') as log:
                    process=subprocess.Popen(self.command(job,camera_name,microphone_name),stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,stderr=log,creationflags=FLAGS)
                    deadline=time.monotonic()+job['seconds']+20
                    while process.poll() is None:
                        if self._path(job['id'],'.stop').exists() or time.monotonic()>deadline:
                            try:process.stdin.write(b'q\n');process.stdin.flush()
                            except (OSError,ValueError):pass
                            try:process.wait(timeout=8)
                            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                            break
                        time.sleep(0.2)
                    process.stdin.close()
                    if process.returncode:raise CaptureError('Запис не вдався. Перевір пристрій і доступ Windows.')
            file=self._path(job['id'],'.mp3' if job['source']=='audio' else '.mp4')
            if not file.exists() or file.stat().st_size<256:
                raise CaptureError('Порожній запис. Спробуй записати ще раз.')
            job['status']='ready'
        except Exception as exc:
            job['status']='error';job['error']=str(exc) if isinstance(exc,CaptureError) else 'Не вдалося запустити запис'
        finally:
            if process and process.poll() is None:process.kill();process.wait(timeout=5)
            if job.get('live_pin'):Path(job['live_pin']).unlink(missing_ok=True)
            job['finished']=time.time()
            try:
                write_state(self._path(job['id'],'.json'),job)
            finally:
                for handle in reversed(locks):handle.__exit__(None,None,None)
                with self.lock:self.workers.pop(job['id'],None)

    def stop(self, identity, owner):
        job=self.get(identity,owner)
        if job['status']=='recording':self._path(identity,'.stop').touch()
        return job

    def file(self, identity, owner):
        job=self.get(identity,owner)
        if job['status']!='ready':raise CaptureError(job.get('error') or 'Запис ще не завершено')
        file=self._path(identity,'.mp3' if job['source']=='audio' else '.mp4')
        if not file.is_file() or file.stat().st_size>MAX_FILE:raise CaptureError('Файл недоступний або завеликий')
        return file

    def delete(self, identity, owner):
        job=self.get(identity,owner)
        if job['status']=='recording':raise CaptureError('Спочатку зупини запис')
        from agent.files import move_to_trash
        file=self._path(identity,'.mp3' if job['source']=='audio' else '.mp4')
        if file.exists():move_to_trash(str(file))
        for suffix in ('.json','.jpg','.frame','.log','.stop'):self._path(identity,suffix).unlink(missing_ok=True)

    def shutdown(self):
        with self.lock:workers=list(self.workers.items())
        for identity,_ in workers:self._path(identity,'.stop').touch()
        for _,thread in workers:thread.join(timeout=10)


service=CaptureService()
