"""Small same-origin API, bound to loopback behind Tailscale Serve."""
import hashlib
import hmac
import json
import logging
import mimetypes
import os
from pathlib import Path, PureWindowsPath
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

STATIC = Path(__file__).parent / "web"
MAX_UPLOAD = 20 * 1024 * 1024
LOG = logging.getLogger("pc_remote")


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Backend:
    def status(self):
        from agent.status import get_status
        return get_status()

    def screenshot(self):
        from agent.control import capture_screen
        return capture_screen()

    def input(self, action):
        from agent.control import control_input
        control_input(action)

    def processes(self):
        from agent.control import list_processes
        return list_processes()

    def terminate(self, pid, created):
        from agent.control import terminate_process
        terminate_process(pid, created)

    def system(self, action):
        from agent.control import execute_system_action
        execute_system_action(action)


class RemoteServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token, files, backend=None):
        if len(token) < 32:
            raise ValueError("Access token must contain at least 32 characters")
        self.token = token
        self.files = Path(files).resolve()
        self.files.mkdir(parents=True, exist_ok=True)
        self.backend = backend or Backend()
        self.confirmations = {}
        self.confirm_lock = threading.Lock()
        self.desktop_lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.failed_auth = {}
        super().__init__(address, Handler)

    def file_path(self, value):
        if not isinstance(value, str) or len(value) > 2048 or "\x00" in value:
            raise APIError(400, "Некоректний шлях")
        # Windows drive names, ADS and traversal must not escape the shared root.
        if ":" in value or "\\" in value or any(p == ".." or PureWindowsPath(p).is_reserved() for p in value.split("/")):
            raise APIError(403, "Шлях поза дозволеною папкою")
        path = (self.files / value).resolve()
        if not path.is_relative_to(self.files):
            raise APIError(403, "Шлях поза дозволеною папкою")
        return path

    def prepare(self, operation, payload):
        if not isinstance(payload, dict):
            raise APIError(400, "Некоректна дія")
        if operation == "system":
            from agent.control import SYSTEM_ACTIONS
            if not isinstance(payload.get("action"), str) or payload["action"] not in SYSTEM_ACTIONS:
                raise APIError(400, "Невідома системна дія")
            return {"action": payload["action"]}
        if operation == "terminate":
            pid, created = payload.get("pid"), payload.get("created")
            if type(pid) is not int or pid <= 4 or pid == os.getpid() or type(created) not in (int, float):
                raise APIError(400, "Некоректний або захищений процес")
            return {"pid": pid, "created": created}
        if operation == "delete":
            path = self.file_path(payload.get("path"))
            if not path.is_file():
                raise APIError(404, "Файл не знайдено")
            stat = path.stat()
            return {"path": path.relative_to(self.files).as_posix(), "size": stat.st_size,
                    "modified": stat.st_mtime_ns, "inode": stat.st_ino}
        raise APIError(400, "Невідома дія")

    def confirm(self, operation, payload):
        prepared = self.prepare(operation, payload)
        ticket = secrets.token_urlsafe(32)
        with self.confirm_lock:
            now = time.monotonic()
            self.confirmations = {k: v for k, v in self.confirmations.items() if v[0] > now}
            if len(self.confirmations) >= 100:
                raise APIError(429, "Забагато запитів підтвердження")
            self.confirmations[ticket] = (now + 60, operation, prepared)
        return ticket

    def consume(self, operation, payload, ticket):
        if not isinstance(ticket, str):
            raise APIError(409, "Потрібне підтвердження")
        with self.confirm_lock:
            record = self.confirmations.pop(ticket, None)
        if not record or record[0] <= time.monotonic() or record[1] != operation:
            raise APIError(409, "Підтвердження прострочене або вже використане")
        prepared = self.prepare(operation, payload)
        if prepared != record[2]:
            raise APIError(409, "Дані змінилися. Оновіть список і підтвердьте ще раз")
        return prepared


class Handler(BaseHTTPRequestHandler):
    server_version = "PC-Helper"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, fmt, *args):
        # Never log credentials, bodies, filenames or URL queries.
        LOG.info("%s %s", self.command, urlsplit(self.path).path)

    def reply(self, status, body, mime="application/json; charset=utf-8", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def auth(self):
        # No cookies or query tokens: cross-site requests cannot carry ambient credentials.
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise APIError(403, "Доступ лише з панелі керування")
        peer = self.client_address[0]
        now = time.monotonic()
        with self.server.rate_lock:
            attempts = [t for t in self.server.failed_auth.get(peer, []) if now - t < 60]
            self.server.failed_auth[peer] = attempts
            if len(attempts) >= 20:
                raise APIError(429, "Забагато спроб входу. Зачекайте хвилину")
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.token
        if not hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(), hashlib.sha256(expected.encode()).digest()):
            with self.server.rate_lock:
                self.server.failed_auth[peer].append(now)
            raise APIError(401, "Неправильний ключ доступу")

    def body(self, limit):
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "Непідтримуваний формат запиту")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError(400, "Некоректний розмір запиту")
        if size < 0 or size > limit:
            raise APIError(413, "Файл або запит завеликий (до 20 МБ)")
        data = self.rfile.read(size)
        if len(data) != size:
            raise APIError(400, "Неповний запит")
        return data

    def json_body(self):
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "Очікується JSON")
        try:
            value = json.loads(self.body(8192), parse_constant=lambda _: None)
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "Некоректний JSON")
        if not isinstance(value, dict):
            raise APIError(400, "Очікується об’єкт JSON")
        return value

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        try:
            url = urlsplit(self.path)
            if url.path.startswith("/api/"):
                self.auth()
                self.api(url, post)
            elif not post:
                self.static(url.path)
            else:
                raise APIError(404, "Сторінку не знайдено")
        except APIError as exc:
            self.reply(exc.status, {"error": exc.message})
        except (ValueError, FileNotFoundError):
            self.reply(400, {"error": "Дані змінилися або запит некоректний. Оновіть сторінку"})
        except PermissionError:
            self.reply(403, {"error": "Windows відмовив у доступі"})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            LOG.exception("Operation failed")
            self.reply(503, {"error": "Дія недоступна. Перевірте сеанс Windows і журнал агента"})

    def static(self, path):
        allowed = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                   "/style.css": "style.css", "/manifest.webmanifest": "manifest.webmanifest",
                   "/sw.js": "sw.js", "/icon.svg": "icon.svg",
                   "/icon-192.png": "icon-192.png", "/icon-512.png": "icon-512.png"}
        if path not in allowed:
            raise APIError(404, "Сторінку не знайдено")
        file = STATIC / allowed[path]
        mime = {".js": "text/javascript", ".webmanifest": "application/manifest+json",
                ".svg": "image/svg+xml"}.get(file.suffix) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        self.reply(200, file.read_bytes(), mime)

    def api(self, url, post):
        query = parse_qs(url.query)
        value = lambda key, default="": query.get(key, [default])[0]
        if not post:
            if url.path == "/api/status":
                return self.reply(200, self.server.backend.status())
            if url.path == "/api/screenshot":
                with self.server.desktop_lock:
                    data = self.server.backend.screenshot()
                return self.reply(200, data, "image/png")
            if url.path == "/api/processes":
                return self.reply(200, {"processes": self.server.backend.processes()})
            if url.path == "/api/files":
                path = self.server.file_path(value("path"))
                if not path.is_dir():
                    raise APIError(404, "Папку не знайдено")
                entries = []
                for entry in path.iterdir():
                    try:
                        if entry.is_symlink() or not entry.resolve().is_relative_to(self.server.files):
                            continue
                        stat = entry.stat()
                        entries.append({"name": entry.name, "directory": entry.is_dir(),
                                        "size": stat.st_size, "path": entry.relative_to(self.server.files).as_posix()})
                        if len(entries) >= 500:
                            break
                    except OSError:
                        continue
                entries.sort(key=lambda f: (not f["directory"], f["name"].casefold()))
                return self.reply(200, {"path": path.relative_to(self.server.files).as_posix(), "entries": entries})
            if url.path == "/api/download":
                with self.server.file_lock:
                    path = self.server.file_path(value("path"))
                    if not path.is_file():
                        raise APIError(404, "Файл не знайдено")
                    if path.stat().st_size > MAX_UPLOAD:
                        raise APIError(413, "Для передавання оберіть файл до 20 МБ")
                    data = path.read_bytes()
                return self.reply(200, data, "application/octet-stream")
            raise APIError(404, "Невідомий запит")

        if url.path == "/api/upload":
            data = self.body(MAX_UPLOAD)
            with self.server.file_lock:
                path = self.server.file_path(value("path"))
                if path == self.server.files or not path.parent.is_dir():
                    raise APIError(400, "Некоректний шлях файлу")
                try:
                    with path.open("xb") as output:
                        output.write(data)
                except FileExistsError:
                    raise APIError(409, "Файл уже існує. Перейменуйте його перед завантаженням")
            return self.reply(201, {"ok": True})

        data = self.json_body()
        if url.path == "/api/input":
            from agent.control import INPUT_ACTIONS
            if not isinstance(data.get("action"), str) or data["action"] not in INPUT_ACTIONS:
                raise APIError(400, "Невідома команда введення")
            with self.server.desktop_lock:
                self.server.backend.input(data["action"])
            return self.reply(200, {"ok": True})
        if url.path == "/api/confirm":
            with self.server.file_lock:
                ticket = self.server.confirm(data.get("operation"), data.get("payload"))
            return self.reply(200, {"confirmation": ticket, "expires_in": 60})
        if url.path == "/api/execute":
            operation, payload = data.get("operation"), data.get("payload")
            with self.server.file_lock:
                prepared = self.server.consume(operation, payload, data.get("confirmation"))
                if operation == "delete":
                    self.server.file_path(prepared["path"]).unlink()
                elif operation == "terminate":
                    self.server.backend.terminate(prepared["pid"], prepared["created"])
                else:
                    self.server.backend.system(prepared["action"])
            LOG.info("Confirmed operation: %s", operation)
            return self.reply(200, {"ok": True})
        raise APIError(404, "Невідомий запит")
