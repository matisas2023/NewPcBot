"""Optional Quick Tunnel launcher. Importing never starts a tunnel."""
import re
import shutil
import subprocess
import threading

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

    def start(self):
        executable = shutil.which("cloudflared")
        if not executable:
            raise RuntimeError("Install cloudflared first: winget install --id Cloudflare.cloudflared -e")
        self.process = subprocess.Popen(
            [executable, "tunnel", "--url", f"http://127.0.0.1:{self.server.server_port}",
             "--http-host-header", PROXY_HOST, "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
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
