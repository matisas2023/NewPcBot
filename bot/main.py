import asyncio
import logging
from aiogram import Bot, Dispatcher
from bot.config import BOT_TOKEN

# Імпортуємо router-и
from bot.handlers import status, screenshot, system, media, fallback
from bot.handlers import start, processes  # нові router-и
from bot.handlers import filesystem
from bot.handlers import media_controls
from bot.handlers import autoreport
from bot.handlers import ux
from bot.handlers import navigation
from pc_remote.runtime import InstanceLock, STATE_DIR, stop_requested


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = Bot(BOT_TOKEN)
    try:
        await run_bot(bot)
    finally:
        from agent.media_capture import service
        await asyncio.to_thread(service.shutdown)
        await bot.session.close()


async def run_bot(bot):
    dp = Dispatcher()

    # Якщо раніше був увімкнений webhook, polling не отримає апдейти.
    # Примусово переходимо на polling-режим.
    await bot.delete_webhook(drop_pending_updates=False)

    # Підключаємо всі router-и
    dp.message.outer_middleware(navigation.NavigationMiddleware())
    dp.include_router(navigation.router)
    dp.include_router(status.router)
    dp.include_router(screenshot.router)
    dp.include_router(system.router)
    dp.include_router(media.router)
    dp.include_router(start.router)
    dp.include_router(processes.router)
    dp.include_router(filesystem.router)
    dp.include_router(media_controls.router)
    dp.include_router(autoreport.router)
    dp.include_router(ux.router)
    dp.include_router(fallback.router)

    print("🤖 Бот запущено!")
    async def watch_stop():
        while not stop_requested():
            await asyncio.sleep(0.5)

    import os
    watcher = None
    try:
        if os.environ.get('PC_HELPER_STOP_FILE'):
            polling = asyncio.create_task(dp.start_polling(bot,handle_signals=False))
            watcher = asyncio.create_task(watch_stop())
            done, _ = await asyncio.wait([polling,watcher],return_when=asyncio.FIRST_COMPLETED)
            if watcher in done and not polling.done():
                try:
                    await dp.stop_polling()
                except RuntimeError:
                    polling.cancel()
            await asyncio.gather(polling,return_exceptions=False)
        else:
            await dp.start_polling(bot)
    finally:
        if watcher:
            watcher.cancel()
            await asyncio.gather(watcher,return_exceptions=True)

if __name__ == "__main__":
    with InstanceLock(STATE_DIR/'telegram.lock'):
        asyncio.run(main())
