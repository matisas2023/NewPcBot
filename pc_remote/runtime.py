"""Local process coordination; never stores account credentials."""
from contextlib import AbstractContextManager
import json
import os
from pathlib import Path
import threading

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / '.pc-helper-runtime'


def write_state(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_state(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


class InstanceLock(AbstractContextManager):
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        if self.handle.tell() == 0:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise RuntimeError('PC Helper: this component is already running')
        return self

    def __exit__(self, *args):
        if self.handle:
            self.handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()


def stop_requested():
    path = os.environ.get('PC_HELPER_STOP_FILE')
    return bool(path and Path(path).exists())
