import random
import asyncio
from pyrogram import enums
from datetime import datetime
from pyrogram.types import Message
import config

# ----------------- Active Users / Sessions -----------------
active_users = set()  # user_id
sessions = {}         # user_id -> partner_id
profile_timers = {}   # user_id -> asyncio.Task
chat_timers = {}      # user_id -> datetime of last message

# Constants
IDLE_CHAT_LIMIT = 15 * 60  # 15 min
PROFILE_TIMEOUT = 5 * 60   # 5 min

# ----------------- User Management -----------------
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

# ----------------- Partner Matching -----------------
def set_partner(user1: int, user2: int):
    """Force set two users as partners."""
    sessions[user1] = user2
    sessions[user2] = user1
    chat_timers[user1] = datetime.utcnow()
    chat_timers[user2] = datetime.utcnow()

# ----------------- Timers -----------------
async def start_profile_timer(user_id: int, send_message):
    """Start profile timer and cancel after timeout."""
    if user_id in profile_timers:
        profile_timers[user_id].cancel()

    async def timeout():
        await asyncio.sleep(PROFILE_TIMEOUT)
        await send_message("⏳ Profile time expired! Please start again.")
        profile_timers.pop(user_id, None)

    task = asyncio.create_task(timeout())
    profile_timers[user_id] = task

async def check_idle_chats(send_message):
    """Loop to disconnect users after idle time."""
    while True:
        now = datetime.utcnow()
        to_remove = []
        for user_id, last_active in list(chat_timers.items()):
            if (now - last_active).total_seconds() > IDLE_CHAT_LIMIT:
                partner_id = sessions.get(user_id)
                if partner_id:
                    await send_message(user_id, "⚠️ Chat closed due to inactivity.")
                    await send_message(partner_id, "⚠️ Chat closed due to inactivity.")
                    to_remove.append(user_id)
                    to_remove.append(partner_id)
        for u in set(to_remove):
            remove_user(u)
        await asyncio.sleep(60)

def update_activity(user_id: int):
    chat_timers[user_id] = datetime.utcnow()
    partner_id = sessions.get(user_id)
    if partner_id:
        chat_timers[partner_id] = datetime.utcnow()

# ----------------- Logging -----------------
async def log_message(app, sender_id, sender_name, msg: Message):
    """
    Logs a message/media to the LOG_CHANNEL.
    """
    text = f"[{datetime.utcnow().isoformat()}Z]\nFrom: <a href='tg://user?id={sender_id}'>{sender_name}</a>"

    if msg.text:
        text += f"\n💬 Text: {msg.text}"
        await app.send_message(config.LOG_CHANNEL, text, parse_mode=enums.ParseMode.HTML)

    elif msg.photo:
        await app.send_photo(
            config.LOG_CHANNEL,
            msg.photo[-1].file_id,
            caption=f"📸 Photo from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )

    # ✅ ADDED: Explicitly handle Video
    elif msg.video:
        await app.send_video(
            config.LOG_CHANNEL,
            msg.video.file_id,
            caption=f"🎥 Video from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
        
    # ✅ ADDED: Explicitly handle Document (Generic File)
    elif msg.document:
        await app.send_document(
            config.LOG_CHANNEL,
            msg.document.file_id,
            caption=f"📎 Document from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )

    elif msg.sticker:
        await app.send_sticker(config.LOG_CHANNEL, msg.sticker.file_id)
        await app.send_message(
            config.LOG_CHANNEL,
            f"🎭 Sticker from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )

    elif msg.animation:
        await app.send_animation(
            config.LOG_CHANNEL,
            msg.animation.file_id,
            caption=f"🎞 GIF/Animation from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )

    else:
        await app.send_message(
            config.LOG_CHANNEL,
            f"⚠️ Unhandled message type from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
