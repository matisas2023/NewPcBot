from aiogram import Router

"""
Deprecated compatibility router.

This module exists to avoid import errors in older entrypoints that still
reference `bot.handlers.other_buttons`. The "Вихід" handler now lives in
bot/handlers/start.py.
"""

router = Router()
