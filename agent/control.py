"""Shared PC operations. Importing this module never performs an action."""
import ctypes
import getpass
import io
import os
import platform
import subprocess
import sys

SYSTEM_ACTIONS = {"Shutdown", "Restart", "Lock", "Logoff", "Sleep", "Hibernate"}
INPUT_ACTIONS = {
    "esc", "enter", "alttab", "click", "move_up", "move_down", "move_left", "move_right",
    "playpause", "next", "prev", "volup", "voldown", "mute",
}


def execute_system_action(action: str):
    if action not in SYSTEM_ACTIONS:
        raise ValueError("Unknown system action")
    system_name = platform.system().lower()
    if system_name == "windows":
        commands = {"Shutdown": ["shutdown", "/s", "/t", "3"],
                    "Restart": ["shutdown", "/r", "/t", "3"], "Logoff": ["shutdown", "/l"]}
        if action in commands:
            subprocess.run(commands[action], check=True, timeout=15)
        elif action == "Lock":
            if not ctypes.windll.user32.LockWorkStation():
                raise OSError("LockWorkStation failed")
        else:
            if not ctypes.windll.powrprof.SetSuspendState(action == "Hibernate", True, False):
                raise OSError("SetSuspendState failed")
        return
    if system_name == "linux":
        commands = {"Shutdown": ["systemctl", "poweroff"], "Restart": ["systemctl", "reboot"],
                    "Logoff": ["loginctl", "terminate-user", getpass.getuser()],
                    "Lock": ["loginctl", "lock-session"], "Sleep": ["systemctl", "suspend"],
                    "Hibernate": ["systemctl", "hibernate"]}
        subprocess.run(commands[action], check=True, timeout=15)
        return
    raise RuntimeError("Unsupported OS for system action")


def capture_screen() -> bytes:
    if sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"):
        raise RuntimeError("Screen capture requires a desktop session")
    try:
        import pyautogui
        output = io.BytesIO()
        pyautogui.screenshot().save(output, format="PNG")
        return output.getvalue()
    except Exception as exc:
        raise RuntimeError("Screen capture unavailable") from exc


def control_input(action: str):
    if action not in INPUT_ACTIONS:
        raise ValueError("Unknown input action")
    try:
        import pyautogui
        moves = {"move_up": (0, -50), "move_down": (0, 50),
                 "move_left": (-50, 0), "move_right": (50, 0)}
        keys = {"playpause": "playpause", "next": "nexttrack", "prev": "prevtrack",
                "volup": "volumeup", "voldown": "volumedown", "mute": "volumemute"}
        if action in moves:
            pyautogui.moveRel(*moves[action])
        elif action == "alttab":
            pyautogui.hotkey("alt", "tab")
        elif action == "click":
            pyautogui.click()
        else:
            pyautogui.press(keys.get(action, action))
    except Exception as exc:
        raise RuntimeError("Desktop input unavailable") from exc


def list_processes():
    import psutil
    result = []
    for proc in psutil.process_iter(["pid", "name", "memory_percent", "create_time"]):
        try:
            info = proc.info
            if info["create_time"] is None:
                continue
            result.append({"pid": info["pid"], "name": info["name"] or "?",
                           "ram": round(info["memory_percent"] or 0, 1), "created": info["create_time"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(result, key=lambda p: p["ram"], reverse=True)[:100]


def terminate_process(pid: int, created: float):
    import psutil
    if pid <= 4 or pid == os.getpid():
        raise ValueError("Protected process")
    proc = psutil.Process(pid)
    if abs(proc.create_time() - created) > 0.001:
        raise ValueError("Process changed; refresh the list")
    proc.terminate()
