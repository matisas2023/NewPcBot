import asyncio
from aiogram import Bot, Dispatcher
from bot.config import BOT_TOKEN

# Імпортуємо router-и
from bot.handlers import status, screenshot, system, media, fallback, other_buttons
from bot.handlers import start, processes  # нові router-и
from bot.handlers import filesystem
from bot.handlers import media_controls
#from bot.handlers import media_player_


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    # Підключаємо всі router-и
    dp.include_router(status.router)
    dp.include_router(screenshot.router)
    dp.include_router(system.router)
    dp.include_router(media.router)
    dp.include_router(other_buttons.router)
    dp.include_router(start.router)
    dp.include_router(processes.router)
    dp.include_router(filesystem.router)
    dp.include_router(media_controls.router)
    #dp.include_router(media_player.router)
    dp.include_router(fallback.router)

    print("🤖 Бот запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
