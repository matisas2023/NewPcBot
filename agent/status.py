import platform
import psutil
import socket
import time


def get_status():
    return {
        "pc": platform.node(),
        "os": platform.system(),
        "uptime": int(time.time() - psutil.boot_time()),
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "ip": socket.gethostbyname(socket.gethostname())
    }
