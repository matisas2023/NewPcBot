"""Single local account, slow password hashes and revocable server-side sessions."""
import hashlib
import hmac
import re
import secrets
import threading
import time
import json
from pathlib import Path

from .runtime import read_state, write_state

ITERATIONS = 600_000
SESSION_SECONDS = 12 * 3600
REMEMBER_SECONDS = 30 * 24 * 3600
COOKIE_NAME = "pc_helper_session"


class LoginError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def create_credentials(username, password):
    if not isinstance(username, str) or not re.fullmatch(r"[\w.-]{3,64}", username):
        raise ValueError("Логін: 3–64 літери, цифри, крапка, дефіс або підкреслення")
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError("Пароль має містити від 12 до 256 символів")
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return {"username": username, "salt": salt, "password_hash": hashed, "iterations": ITERATIONS}


class Account:
    def __init__(self, credentials, session_store=None):
        if (not isinstance(credentials, dict) or not isinstance(credentials.get("username"), str)
                or credentials.get("iterations") != ITERATIONS):
            raise ValueError("Run python -m pc_remote --setup to configure login and password")
        try:
            self.salt = bytes.fromhex(credentials["salt"])
            self.password_hash = bytes.fromhex(credentials["password_hash"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("Invalid account configuration; run --setup again")
        if len(self.salt) != 16 or len(self.password_hash) != 32:
            raise ValueError("Invalid account configuration; run --setup again")
        self.username = credentials["username"]
        self.sessions = {}
        self.attempts = []
        self.lock = threading.Lock()
        self.session_store = Path(session_store) if session_store else None
        self.fingerprint = hashlib.sha256(json.dumps(credentials,sort_keys=True).encode()).hexdigest()
        self._restore()

    def _restore(self):
        if not self.session_store:
            return
        saved=read_state(self.session_store)
        if not isinstance(saved,dict) or saved.get('account') != self.fingerprint or not isinstance(saved.get('sessions'),dict):
            return
        for key, value in list(saved['sessions'].items())[:5]:
            if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key) or not isinstance(value,dict):
                continue
            expires=value.get('expires_at')
            if type(expires) not in (int,float) or not time.time() < expires <= time.time()+REMEMBER_SECONDS:
                continue
            if not isinstance(value.get('csrf'),str) or not isinstance(value.get('origin'),str):
                continue
            self.sessions[key]={'id':key,'csrf':value['csrf'],'origin':value['origin'],
                'expires_at':expires,'expires':time.monotonic()+expires-time.time(),
                'remembered':True,'ttl':REMEMBER_SECONDS}

    def _persist(self):
        if self.session_store:
            sessions={key:{'csrf':value['csrf'],'origin':value['origin'],'expires_at':value['expires_at']}
                for key,value in self.sessions.items() if value.get('remembered') and value['expires']>time.monotonic()}
            write_state(self.session_store,{'account':self.fingerprint,'sessions':sessions})

    def login(self, username, password, origin, remember=False):
        with self.lock:
            now = time.monotonic()
            self.attempts = [t for t in self.attempts if now - t < 60]
            # Global limit: forwarded client IP headers are never trusted for bypassing it.
            if len(self.attempts) >= 10:
                raise LoginError(429, "Забагато спроб входу. Зачекайте хвилину")
            self.attempts.append(now)
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 64 or len(password) > 256:
            raise LoginError(401, "Неправильний логін або пароль")
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), self.salt, ITERATIONS)
        name_ok = hmac.compare_digest(username.encode(), self.username.encode())
        if not (hmac.compare_digest(hashed, self.password_hash) and name_ok):
            raise LoginError(401, "Неправильний логін або пароль")
        if type(remember) is not bool:
            raise LoginError(400,'Некоректне налаштування збереження входу')
        ttl=REMEMBER_SECONDS if remember else SESSION_SECONDS
        token = secrets.token_urlsafe(32)
        key = hashlib.sha256(token.encode()).hexdigest()
        session = {"id": key, "csrf": secrets.token_urlsafe(32), "origin": origin,
                   "expires": time.monotonic() + ttl, 'expires_at':time.time()+ttl,
                   'remembered':remember,'ttl':ttl}
        with self.lock:
            self.sessions = {k: s for k, s in self.sessions.items() if s["expires"] > time.monotonic()}
            if len(self.sessions) >= 5:
                oldest = min(self.sessions, key=lambda k: self.sessions[k]["expires"])
                del self.sessions[oldest]
            self.sessions[key] = session
            self._persist()
        return token, session

    def authenticate(self, token, origin):
        if not isinstance(token, str) or len(token) > 256:
            raise LoginError(401, "Увійдіть за логіном і паролем")
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            session = self.sessions.get(key)
            if not session or session["expires"] <= time.monotonic() or session["origin"] != origin:
                self.sessions.pop(key, None)
                self._persist()
                raise LoginError(401, "Сеанс завершено. Увійдіть ще раз")
            return session.copy()

    def logout(self, session):
        with self.lock:
            self.sessions.pop(session["id"], None)
            self._persist()
