import asyncio
from typing import Dict

# user_id -> asyncio.Task
scheduled_tasks: Dict[int, asyncio.Task] = {}


async def _delayed_action(delay: int, action_cb):
    await asyncio.sleep(delay)
    await action_cb()


def schedule_action(user_id: int, delay: int, action_cb):
    cancel_scheduled_action(user_id)

    task = asyncio.create_task(_delayed_action(delay, action_cb))
    scheduled_tasks[user_id] = task


def cancel_scheduled_action(user_id: int):
    task = scheduled_tasks.pop(user_id, None)
    if task:
        task.cancel()


def has_scheduled_action(user_id: int) -> bool:
    return user_id in scheduled_tasks
