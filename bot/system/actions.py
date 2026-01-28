import subprocess
import ctypes


def execute_system_action(action: str):
    if action == "Shutdown":
        subprocess.run(["shutdown", "/s", "/t", "0"], shell=True)

    elif action == "Restart":
        subprocess.run(["shutdown", "/r", "/t", "0"], shell=True)

    elif action == "Logoff":
        subprocess.run(["shutdown", "/l"], shell=True)

    elif action == "Lock":
        ctypes.windll.user32.LockWorkStation()

    elif action == "Sleep":
        ctypes.windll.powrprof.SetSuspendState(False, True, False)

    elif action == "Hibernate":
        ctypes.windll.powrprof.SetSuspendState(True, True, False)
