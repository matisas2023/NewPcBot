"""Phone handoff containing only the public address, never credentials."""
from urllib.parse import urlsplit

from .runtime import STATE_DIR, read_state


def public_url(state):
    if not isinstance(state, dict) or state.get('state') not in ('online', 'configured'):
        return None
    url = state.get('url')
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
        parsed.port
    except ValueError:
        return None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        return None
    return url


def show_phone():
    import tkinter as tk
    from tkinter import ttk
    import qrcode
    from PIL import ImageTk
    root = tk.Tk()
    root.title('PC Helper — підключити телефон')
    root.geometry('440x540')
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Відскануй камерою телефона', font=('Segoe UI', 15)).pack(pady=10)
    image = ttk.Label(frame)
    image.pack()
    address = tk.StringVar()
    field = ttk.Entry(frame, textvariable=address, state='readonly')
    field.pack(fill='x', pady=10)
    hint = ttk.Label(frame, wraplength=390, justify='left')
    hint.pack(pady=10)
    def copy():
        if address.get():
            root.clipboard_clear()
            root.clipboard_append(address.get())
    ttk.Button(frame, text='Скопіювати адресу', command=copy).pack()
    current = object()
    def refresh():
        nonlocal current
        connection = read_state(STATE_DIR/'connection.json')
        url = public_url(connection)
        if url != current:
            current = url
            address.set(url or '')
            if url:
                qr = qrcode.make(url).convert('RGB').resize((300, 300))
                image.photo = ImageTk.PhotoImage(qr)
                image.configure(image=image.photo)
                hint.configure(text='Відкрий адресу та введи свій логін і пароль. Познач «Запам’ятати вхід» на власному телефоні. '+('Адреса зберігається, поки незмінна біла IP-адреса.' if connection.get('kind')=='direct' else 'Тимчасова адреса змінюється після перезапуску тунелю.'))
            else:
                image.configure(image='')
                image.photo = None
                hint.configure(text='Зовнішнє HTTPS-підключення ще недоступне. Перевір стан підключення та налаштування портів; QR-код з’явиться автоматично. Локальна панель на ПК доступна за адресою http://127.0.0.1:8765.')
        root.after(2000, refresh)
    refresh()
    root.mainloop()
