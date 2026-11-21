"""Optional Quick Tunnel launcher. Importing never starts a tunnel."""
import re
import shutil
import subprocess
import threading
import os
from pathlib import Path

from .server import PROXY_HOST

URL_PATTERN = re.compile(r"https://(?!api\.|www\.)[a-z0-9-]+\.trycloudflare\.com\b")


class QuickTunnel:
    def __init__(self, server):
        self.server = server
        self.process = None
        self.reader = None
        self.ready = threading.Event()
        self.url = None
        self.last_error = None
        self.close_lock = threading.Lock()
        self.closed = False

    def start(self):
        executable = shutil.which("cloudflared")
        if not executable and os.name == 'nt':
            for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
                candidate = Path(os.environ.get(variable, '')) / 'cloudflared' / 'cloudflared.exe'
                if candidate.is_file():
                    executable = str(candidate)
                    break
        if not executable:
            raise RuntimeError("Install cloudflared first: winget install --id Cloudflare.cloudflared -e")
        with self.close_lock:
            if self.closed:
                raise RuntimeError('Tunnel startup cancelled')
            self.process = subprocess.Popen(
                [executable, "tunnel", "--url", f"http://127.0.0.1:{self.server.server_port}",
                 "--http-host-header", PROXY_HOST, "--no-autoupdate"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
        if not self.ready.wait(60) or not self.url or self.process.poll() is not None:
            self.close()
            detail = (" " + self.last_error) if self.last_error else ""
            raise RuntimeError("Cloudflare tunnel did not start. Check internet and cloudflared configuration; see pc_remote/README.md." + detail)
        return self.url

    def _read(self):
        try:
            for line in self.process.stdout:
                if "ERR" in line or "failed" in line.lower() or "error" in line.lower():
                    self.last_error = line.strip()[-300:]
                match = URL_PATTERN.search(line)
                if match and self.url is None:
                    self.url = match.group(0)
                    self.server.public_origin = self.url
                    self.ready.set()
        finally:
            self.ready.set()

    def close(self):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
            self.ready.set()
            if self.process:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=5)
                if self.reader and self.reader is not threading.current_thread():
                    self.reader.join(timeout=2)
                if self.process.stdout:
                    self.process.stdout.close()


class TunnelManager:
    """Retry only the connection. Never retry or queue a PC command."""
    def __init__(self, server, factory=QuickTunnel):
        self.server = server
        self.factory = factory
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.current = None
        self.thread = None
        self.state = {'state':'local', 'url':None, 'retry_in':0}

    def snapshot(self):
        with self.lock:
            return self.state.copy()

    def set_state(self, state, url=None, retry_in=0):
        with self.lock:
            self.state = {'state':state, 'url':url, 'retry_in':retry_in}

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        delay = 5
        while not self.stop_event.is_set():
            tunnel = self.factory(self.server)
            with self.lock:
                self.current = tunnel
            try:
                self.set_state('connecting')
                url = tunnel.start()
                if self.stop_event.is_set():
                    break
                self.set_state('online', url)
                print('Open on Android:', url, flush=True)
                delay = 5
                while not self.stop_event.wait(1):
                    if tunnel.process.poll() is not None:
                        break
            except (RuntimeError, OSError):
                pass
            finally:
                tunnel.close()
                # Old origins must not stay trusted after a tunnel disconnects.
                self.server.public_origin = None
                with self.lock:
                    self.current = None
            if self.stop_event.is_set():
                break
            self.set_state('retrying', retry_in=delay)
            if self.stop_event.wait(delay):
                break
            delay = min(delay * 2, 120)
        self.set_state('stopped')

    def stop(self):
        self.stop_event.set()
        with self.lock:
            current = self.current
        if current:
            current.close()
        if self.thread:
            self.thread.join(timeout=10)
