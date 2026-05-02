# Debian Server Bot

Окремий Telegram-бот для керування **лише Debian сервером**.

## Можливості
- Статус сервера (`/status`, `/diag`)
- Диски та файлова система (`/disk`, `/fs`)
- Процеси (`/top`, `/services`)
- Мережа (`/net`)
- Системні дії (`/reboot`, `/shutdown`, `/lock`, `/restart_service <name>`)
- Музичний сервіс/Navidrome:
  - `/music_status`
  - `/music_download`
  - `/music_log`
  - `/music_restart`
  - `/music_space`

## Налаштування
Створіть `.env` (або задайте env змінні):
- `DEBIAN_BOT_TOKEN`
- `DEBIAN_ALLOWED_USERS` (CSV user_id)
- `DEBIAN_ALLOWED_CHATS` (CSV chat_id, опціонально)

## Запуск
```bash
python -m debian_server_bot.main
```

## Примітка безпеки
- Бот надає адміністративні команди (reboot/shutdown/restart service), тому запускайте його тільки в довіреному чаті.
- Обовʼязково вкажіть `DEBIAN_ALLOWED_USERS` і за потреби `DEBIAN_ALLOWED_CHATS`.
