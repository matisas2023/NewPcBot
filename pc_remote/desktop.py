"""Windows tray supervisor and reversible per-user startup."""
import argparse
from collections import deque
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import webbrowser

from .runtime import ROOT, STATE_DIR, InstanceLock, read_state, write_state

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'PC Helper'


def startup_command(public=False, origin=None):
    executable = Path(sys.executable).with_name('pythonw.exe')
    if not executable.is_file():
        executable = Path(sys.executable)
    args = [str(executable), '-X', 'utf8', '-m', 'pc_remote.desktop', '--root', str(ROOT)]
    if public:
        args.append('--public')
    if origin:
        args.extend(['--origin', origin])
    # -m requires the project working directory, which Run entries cannot set.
    # Use a fixed launcher path instead; the launcher selects its own project root.
    args[3:5] = [str(ROOT/'pc_remote'/'tray_launcher.py')]
    return subprocess.list2cmdline(args)


def set_startup(enabled, public=False, origin=None):
    if os.name != 'nt':
        raise RuntimeError('Automatic startup is available on Windows')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command(public, origin))
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def startup_enabled():
    if os.name != 'nt':
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, RUN_NAME)[0])
    except FileNotFoundError:
        return False


class Child:
    def __init__(self, name, args, logger):
        self.name, self.args, self.logger = name, args, logger
        self.process = None
        self.stop_file = None
        self.next_start = 0
        self.delay = 5
        self.started = 0
        self.recent = deque(maxlen=3)

    def start(self):
        self.stop_file = STATE_DIR/f'{self.name}-{uuid.uuid4().hex}.stop'
        env = os.environ.copy()
        env['PC_HELPER_STOP_FILE'] = str(self.stop_file)
        self.process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', *self.args], cwd=ROOT,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.started = time.monotonic()
        threading.Thread(target=self.drain, args=(self.process,), daemon=True).start()

    def drain(self, process):
        for line in process.stdout:
            self.logger.info('%s: %s', self.name, line.rstrip())
        process.stdout.close()

    def tick(self):
        now = time.monotonic()
        if self.process and self.process.poll() is not None:
            self.recent.append(self.process.returncode)
            self.delay = 5 if now - self.started > 60 else min(self.delay * 2, 120)
            self.next_start = now + self.delay
            self.process = None
            if self.stop_file:
                self.stop_file.unlink(missing_ok=True)
        if not self.process and now >= self.next_start:
            try:
                self.start()
            except OSError:
                self.next_start = now + 30
                self.logger.exception('Could not start %s', self.name)

    def snapshot(self):
        return {'state':'running' if self.process and self.process.poll() is None else 'retrying',
                'pid': self.process.pid if self.process and self.process.poll() is None else None,
                'last_exit': self.recent[-1] if self.recent else None}

    def stop(self):
        if self.process and self.process.poll() is None:
            self.stop_file.touch()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.process = None
        if self.stop_file:
            self.stop_file.unlink(missing_ok=True)


class Supervisor:
    def __init__(self, public=False, origin=None):
        self.public, self.origin = public, origin
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f'pc-helper-desktop.{id(self)}')
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(STATE_DIR/'desktop.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.logger.addHandler(handler)
        self.log_handler = handler
        agent_args = ['pc_remote'] + (['--public'] if public else []) + (['--origin',origin] if origin else [])
        self.children = [Child('agent',agent_args,self.logger), Child('telegram',['bot.main'],self.logger)]
        self.enabled = True
        self.lock = threading.RLock()
        self.done = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        while not self.done.is_set():
            with self.lock:
                if self.enabled:
                    for child in self.children:
                        child.tick()
                write_state(STATE_DIR/'desktop.json', {'pid':os.getpid(),'enabled':self.enabled,
                            'services':{c.name:c.snapshot() for c in self.children}})
            self.done.wait(1)

    def pause(self):
        with self.lock:
            self.enabled = False
            for child in self.children:
                child.stop()

    def resume(self):
        with self.lock:
            for child in self.children:
                child.next_start = 0
            self.enabled = True

    def restart(self):
        self.pause()
        self.resume()

    def stop(self):
        self.done.set()
        self.pause()
        if self.thread:
            self.thread.join(timeout=3)
        write_state(STATE_DIR/'desktop.json', {'pid':os.getpid(),'enabled':False,'services':{}})
        self.logger.removeHandler(self.log_handler)
        self.log_handler.close()


def show_status():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title('PC Helper — стан підключення')
    root.geometry('560x330')
    frame = ttk.Frame(root,padding=20)
    frame.pack(fill='both',expand=True)
    text = tk.StringVar()
    ttk.Label(frame,textvariable=text,wraplength=520,justify='left').pack(anchor='w')
    def refresh():
        desktop = read_state(STATE_DIR/'desktop.json')
        connection = read_state(STATE_DIR/'connection.json')
        labels = {'running':'Процес запущений','retrying':'Повторне підключення','online':'HTTPS підключено',
                  'connecting':'Підключення HTTPS','local':'Лише локальний доступ','configured':'Власний HTTPS-проксі',
                  'stopped':'Зупинено'}
        services = desktop.get('services',{})
        lines = ['Telegram: '+labels.get(services.get('telegram',{}).get('state'),'Зупинено'),
                 'Вебагент: '+labels.get(services.get('agent',{}).get('state'),'Зупинено'),
                 'Тунель: '+labels.get(connection.get('state'),'Немає даних'),
                 'Локальна панель: http://127.0.0.1:8765',
                 'Зовнішня адреса: '+(connection.get('url') or 'ще недоступна'),
                 'Автозапуск: '+('увімкнений' if startup_enabled() else 'вимкнений')]
        text.set('\n\n'.join(lines))
        root.after(2000,refresh)
    refresh()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description='PC Helper Windows tray')
    parser.add_argument('--root',type=Path,default=ROOT)
    connection = parser.add_mutually_exclusive_group()
    connection.add_argument('--public',action='store_true')
    connection.add_argument('--origin')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--install-startup',action='store_true')
    actions.add_argument('--remove-startup',action='store_true')
    actions.add_argument('--status',action='store_true')
    args = parser.parse_args()
    os.chdir(args.root)
    if args.install_startup or args.remove_startup:
        set_startup(args.install_startup,args.public,args.origin)
        print('Startup enabled' if args.install_startup else 'Startup disabled')
        return
    if args.status:
        show_status()
        return
    import pystray
    from PIL import Image
    try:
        with InstanceLock(STATE_DIR/'desktop.lock'):
            supervisor = Supervisor(args.public,args.origin)
            def status_window(*_):
                subprocess.Popen([sys.executable,'-X','utf8','-m','pc_remote.desktop','--status'],cwd=ROOT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            def quit_app(icon,*_):
                icon.stop()
            icon = pystray.Icon('pc-helper',Image.open(ROOT/'pc_remote/web/icon-192.png'),'PC Helper',menu=pystray.Menu(
                pystray.MenuItem('Стан підключення',status_window,default=True),
                pystray.MenuItem('Відкрити панель',lambda *_:webbrowser.open('http://127.0.0.1:8765')),
                pystray.MenuItem('Перезапустити служби',lambda *_:supervisor.restart()),
                pystray.MenuItem('Зупинити служби',lambda *_:supervisor.pause()),
                pystray.MenuItem('Запустити служби',lambda *_:supervisor.resume()),
                pystray.MenuItem('Автозапуск',lambda *_:set_startup(not startup_enabled(),args.public,args.origin),checked=lambda _:startup_enabled()),
                pystray.MenuItem('Вийти',quit_app)))
            supervisor.start()
            try:
                icon.run()
            finally:
                supervisor.stop()
    except RuntimeError as exc:
        print(str(exc))


if __name__ == '__main__':
    main()
