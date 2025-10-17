# utils.py

import random
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from datetime import datetime, timedelta
import config

# ----------------- Active Users / Sessions -----------------
active_users = set()  # user_id
sessions = {}         # user_id -> partner_id
profile_timers = {}   # user_id -> asyncio.Task
chat_timers = {}      # user_id -> datetime of last message
waiting_users = set() # Move waiting_users here to avoid circular import

# Constants
IDLE_CHAT_LIMIT = 15 * 60  # 15 min
PROFILE_TIMEOUT = 5 * 60   # 5 min
AUTO_DELETE_DELAY = 3600   # 1 hour
SEARCH_TIMEOUT = 120       # 2 minutes

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

# ----------------- Search Functions -----------------
async def send_search_progress(client, user_id: int):
    """Send periodic updates about search progress."""
    elapsed = 0
    
    while user_id in waiting_users and elapsed < SEARCH_TIMEOUT:
        await asyncio.sleep(30)  # Update every 30 seconds
        elapsed += 30
        
        if user_id in waiting_users:
            remaining = SEARCH_TIMEOUT - elapsed
            minutes = remaining // 60
            seconds = remaining % 60
            
            try:
                await client.send_message(
                    user_id,
                    f"⏳ **ꜱᴛɪʟʟ ꜱᴇᴀʀᴄʜɪɴɢ...**\n"
                    f"ᴛɪᴍᴇ ʀᴇᴍᴀɪɴɪɴɢ: {minutes:02d}:{seconds:02d}\n"
                    f"ᴜꜱᴇ /ᴄᴀɴᴄᴇʟ ᴛᴏ ꜱᴛᴏᴘ ꜱᴇᴀʀᴄʜɪɴɢ."
                )
            except Exception as e:
                print(f"[SEARCH] Error sending progress update to {user_id}: {e}")
                break
                
async def check_partner_wait(client, user_id: int, wait_time: int = SEARCH_TIMEOUT):
    """
    Check if user is still waiting for a partner after wait_time seconds.
    If still waiting, send a "no partner found" message and remove from waiting list.
    """
    await asyncio.sleep(wait_time)
    
    # Check if user is still in waiting list
    if user_id in waiting_users:
        try:
            # Remove from waiting list
            waiting_users.discard(user_id)
            
            # Send "no partner found" message
            await client.send_message(
                user_id, 
                "😔 **ꜱᴏʀʀʏ, ɴᴏ ᴘᴀʀᴛɴᴇʀ ꜰᴏᴜɴᴅ ʀɪɢʜᴛ ɴᴏᴡ.**\n\n"
                "ᴛʀʏ ꜱᴇᴀʀᴄʜɪɴɢ ᴀɢᴀɪɴ ɪɴ ᴀ ꜰᴇᴡ ᴍɪɴᴜᴛᴇꜱ ᴏʀ ᴛʀʏ ᴅɪꜰꜰᴇʀᴇɴᴛ ᴛɪᴍᴇꜱ ᴏꜰ ᴛʜᴇ ᴅᴀʏ ᴡʜᴇɴ ᴍᴏʀᴇ ᴜꜱᴇʀꜱ ᴀʀᴇ ᴀᴄᴛɪᴠᴇ."
            )
            
            # Log the timeout
            print(f"[SEARCH] User {user_id} timed out after {wait_time} seconds without finding a partner")
            
        except Exception as e:
            print(f"[SEARCH] Error sending timeout message to {user_id}: {e}")

async def cancel_search(user_id: int):
    """Cancel search for a user (could be used by multiple modules)"""
    if user_id in waiting_users:
        waiting_users.discard(user_id)
        return True
    return False

def update_activity(user_id: int):
    chat_timers[user_id] = datetime.utcnow()
    partner_id = sessions.get(user_id)
    if partner_id:
        chat_timers[partner_id] = datetime.utcnow()

# ----------------- Auto-Delete Functions -----------------
autodelete_enabled_chats = set()

async def load_autodelete_state(db_client):
    """Loads all autodelete-enabled groups from the database into the global set."""
    global autodelete_enabled_chats
    try:
        all_enabled = await db_client.get_all_autodelete_enabled_chats()
        if all_enabled:
            autodelete_enabled_chats = set(all_enabled)
        print(f"[AUTODELETE] Loaded {len(autodelete_enabled_chats)} autodelete-enabled groups from DB.")
    except Exception as e:
        print(f"[AUTODELETE] Error loading state: {e}")

async def schedule_deletion(client: Client, chat_id: int, message_ids: list[int], delay: int = AUTO_DELETE_DELAY):
    """Schedules a list of messages to be deleted after a delay."""
    await asyncio.sleep(delay)
    
    try:
        await client.delete_messages(chat_id, message_ids)
        print(f"[AUTODELETE] Deleted messages {message_ids} in chat {chat_id}")
    except Exception as e:
        print(f"[AUTODELETE] Could not delete messages {message_ids}: {e}")

async def schedule_autodelete(message: Message, delay: int = AUTO_DELETE_DELAY):
    """
    Auto-delete any message after `delay` seconds.
    Default: 3600 seconds = 1 hour.
    """
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass

async def safe_reply(message: Message, text: str, **kwargs):
    """
    Reply and schedule auto-delete if needed.
    """
    sent = await message.reply_text(text, **kwargs)
    await schedule_autodelete(sent)
    return sent

# ----------------- Utility Functions -----------------
def get_online_users_count(minutes: int = 5) -> int:
    """
    Returns the count of users active in the last 'x' minutes.
    This is used by the /status command.
    """
    time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
    count = 0
    for timestamp in chat_timers.values():
        if timestamp > time_threshold:
            count += 1
    return count

# ----------------- Logging -----------------
async def log_message(app, sender_id, sender_name, msg: Message):
    """
    Logs a message/media to the LOG_USERS.
    """
    text = f"[{datetime.utcnow().isoformat()}Z]\nFrom: <a href='tg://user?id={sender_id}'>{sender_name}</a>"

    if msg.text:
        text += f"\n💬 Text: {msg.text}"
        await app.send_message(config.LOG_USERS, text, parse_mode=enums.ParseMode.HTML)

    elif msg.photo:
        await app.send_photo(
            config.LOG_USERS,
            msg.photo[-1].file_id,
            caption=f"📸 Photo from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
    elif msg.video:
        await app.send_video(
            config.LOG_USERS,
            msg.video.file_id,
            caption=f"🎥 Video from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
    elif msg.document:
        await app.send_document(
            config.LOG_USERS,
            msg.document.file_id,
            caption=f"📎 Document from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
    elif msg.sticker:
        await app.send_sticker(config.LOG_USERS, msg.sticker.file_id)
        await app.send_message(
            config.LOG_USERS,
            f"🎭 Sticker from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
    elif msg.animation:
        await app.send_animation(
            config.LOG_USERS,
            msg.animation.file_id,
            caption=f"🎞 GIF/Animation from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
    else:
        await app.send_message(
            config.LOG_USERS,
            f"⚠️ Unhandled message type from <a href='tg://user?id={sender_id}'>{sender_name}</a>",
            parse_mode=enums.ParseMode.HTML
        )
