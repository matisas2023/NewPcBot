# PC Helper

Telegram-бот і мобільна панель для керування власним ПК.

- Telegram: `python -m bot.main` (`BOT_TOKEN` і `ALLOWED_USERS` у `.env`).
- Android без VPN: `python -m pc_remote --setup`, потім `python -m pc_remote --public`.
  Інструкція з HTTPS та встановлення PWA: [pc_remote/README.md](pc_remote/README.md).
- Окремий Debian-бот: [debian_server_bot/README.md](debian_server_bot/README.md).

Залежності: `python -m pip install -r requirements.txt`.

Windows: запуск із трею — `pythonw -m pc_remote.desktop --public`.
Автозапуск після входу — `python -m pc_remote.desktop --install-startup --public`.
Агент працює локально навіть при недоступному тунелі. Деталі й обмеження —
у [мобільній інструкції](pc_remote/README.md).

Простий запуск Windows: двічі натисни **PC Helper.cmd**. Якщо облікового
запису ще немає, відкриється вікно створення логіна та пароля.
У меню значка PC Helper у треї: **Логін і пароль** — змінити дані,
**Підключити телефон (QR)** — відкрити актуальну зовнішню адресу камерою телефона.
На сторінці входу можна показати пароль та обрати **Запам’ятати вхід на 30 днів**.
Ключі для вебпанелі не потрібні. Тимчасова HTTPS-адреса змінюється після
перезапуску тунелю; для нової адреси потрібно ввійти знову.
