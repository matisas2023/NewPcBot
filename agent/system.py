import os

def shutdown():
    os.system("shutdown /s /t 5")

def reboot():
    os.system("shutdown /r /t 5")

def lock():
    os.system("rundll32.exe user32.dll,LockWorkStation")
