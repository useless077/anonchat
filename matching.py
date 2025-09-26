import random
import asyncio
from datetime import datetime, timedelta

active_users = set()  # Users available for pairing
sessions = {}  # user_id -> partner_id
profile_timers = {}  # user_id -> timeout task
chat_timers = {}  # user_id -> last activity timestamp

IDLE_CHAT_LIMIT = 15 * 60  # 15 minutes
PROFILE_TIMEOUT = 5 * 60  # 5 minutes


def add_user(user_id: int):
    active_users.add(user_id)


def remove_user(user_id: int):
    active_users.discard(user_id)
    partner_id = sessions.pop(user_id, None)
    if partner_id:
        sessions.pop(partner_id, None)
    if user_id in profile_timers:
        profile_timers[user_id].cancel()
        profile_timers.pop(user_id, None)
    if user_id in chat_timers:
        chat_timers.pop(user_id, None)


def get_partner(user_id: int):
    if user_id in sessions:
        return sessions[user_id]

    candidates = [u for u in active_users if u != user_id and u not in sessions]
    if not candidates:
        return None

    partner = random.choice(candidates)
    sessions[user_id] = partner
    sessions[partner] = user_id
    chat_timers[user_id] = datetime.utcnow()
    chat_timers[partner] = datetime.utcnow()
    return partner


def set_partner(user1: int, user2: int):
    sessions[user1] = user2
    sessions[user2] = user1
    chat_timers[user1] = datetime.utcnow()
    chat_timers[user2] = datetime.utcnow()


async def start_profile_timer(user_id: int, send_message):
    """Wait for PROFILE_TIMEOUT seconds, then cancel profile update."""
    if user_id in profile_timers:
        profile_timers[user_id].cancel()

    async def timeout():
        await asyncio.sleep(PROFILE_TIMEOUT)
        await send_message("⏳ Time expired! Please start updating your profile again.")
        profile_timers.pop(user_id, None)

    task = asyncio.create_task(timeout())
    profile_timers[user_id] = task


async def check_idle_chats(send_message):
    """Loop that checks for idle chats and disconnects after IDLE_CHAT_LIMIT seconds."""
    while True:
        now = datetime.utcnow()
        to_remove = []
        for user_id, last_active in chat_timers.items():
            if (now - last_active).total_seconds() > IDLE_CHAT_LIMIT:
                partner_id = sessions.get(user_id)
                if partner_id:
                    await send_message(user_id, "⚠️ Chat closed due to inactivity.")
                    await send_message(partner_id, "⚠️ Chat closed due to inactivity.")
                    to_remove.append(user_id)
                    to_remove.append(partner_id)
        for u in set(to_remove):
            remove_user(u)
        await asyncio.sleep(60)  # Check every 1 min


def update_activity(user_id: int):
    chat_timers[user_id] = datetime.utcnow()
    partner_id = sessions.get(user_id)
    if partner_id:
        chat_timers[partner_id] = datetime.utcnow()
