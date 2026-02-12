import random
import asyncio
import hashlib  # Required for duplicate check logic
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
IDLE_CHAT_LIMIT = 30 * 60  # 30 min
PROFILE_TIMEOUT = 5 * 60   # 5 min
AUTO_DELETE_DELAY = 3600   # 1 hour
SEARCH_TIMEOUT = 120       # 2 minutes

# ----------------- Spam Filter Configuration -----------------
# Keywords found in your logs that are repetitive/spam
SPAM_KEYWORDS = [
    "16 and 17 years", 
    "Fremdysuckeckbot", 
    "unsatisfied high society", 
    "meet then payment", 
    "female massage therapist", 
    "Any girl Or couple",
    "Housewife here to answer",
    "Ayurvedic Massage",
    "t.me/Fremdysuckeckbot"
]

# Keep track of recently logged messages to prevent duplicates (flood control)
recent_logs_cache = set()

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

# ----------------- IDLE CHAT CHECKER -----------------
async def check_idle_chats(client: Client):
    """
    Loop to disconnect users after 30 minutes of inactivity.
    This task must be started in main.py using asyncio.create_task.
    """
    print("[IDLE CHECKER] Started 30-minute idle chat checker...")
    while True:
        now = datetime.utcnow()
        to_remove = []
        
        # Check all active chats
        for user_id, last_active in list(chat_timers.items()):
            if (now - last_active).total_seconds() > IDLE_CHAT_LIMIT:
                partner_id = sessions.get(user_id)
                
                if partner_id:
                    print(f"[IDLE CHECKER] Closing idle chat between {user_id} and {partner_id}")
                    
                    try:
                        # 1. Notify both users
                        await client.send_message(user_id, "⚠️ **Chat closed due to 30 minutes of inactivity.**")
                        await client.send_message(partner_id, "⚠️ **Chat closed due to 30 minutes of inactivity.**")
                    except Exception as e:
                        print(f"[IDLE CHECKER] Failed to notify user: {e}")

                    # 2. Cleanup Database
                    try:
                        await db.reset_partners(user_id, partner_id)
                        await db.update_status(user_id, "idle")
                        await db.update_status(partner_id, "idle")
                    except Exception as e:
                        print(f"[IDLE CHECKER] Failed to update DB: {e}")

                    # 3. Mark for removal from utils state
                    to_remove.append(user_id)
                    to_remove.append(partner_id)
        
        # 4. Cleanup Utils State
        for u in set(to_remove):
            remove_user(u)
            
        await asyncio.sleep(60) # Check every minute

# ----------------- Search Functions -----------------
async def send_search_progress(client, user_id: int, message_obj: Message):
    """
    Updates the search message with a countdown timer instead of sending new messages.
    """
    start_time = datetime.utcnow()
    dots_count = 0
    
    try:
        # Keep running while user is in waiting list
        while user_id in waiting_users:
            # Calculate elapsed time
            elapsed = int((datetime.utcnow() - start_time).total_seconds())
            
            # Check if we exceeded timeout (safety break)
            if elapsed >= SEARCH_TIMEOUT:
                break
            
            remaining = SEARCH_TIMEOUT - elapsed
            minutes = remaining // 60
            seconds = remaining % 60
            
            # Animate dots (1, 2, 3)
            dots_count = (dots_count % 3) + 1 
            
            text = (
                f"🔍 **sᴇᴀʀᴄʜɪɴɢ ꜰᴏʀ ᴀ ᴘᴀʀᴛɴᴇʀ{'.' * dots_count}**\n"
                f"⏱️ **ᴛɪᴍᴇ ʀᴇᴍᴀɪɴɪɴɢ:** {minutes:02d}:{seconds:02d}\n"
                f"⚠️ **ᴜꜱᴇ /ᴄᴀɴᴄᴇʟ ᴛᴏ ꜱᴛᴏᴘ ꜱᴇᴀʀᴄʜɪɴɢ.**"
            )
            
            try:
                # CHANGED: Edit the message instead of sending a new one
                await message_obj.edit_text(text)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                # If edit fails (e.g. message deleted by user), stop loop
                break
            
            await asyncio.sleep(1) # Update every 1 second for accurate timer
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[SEARCH_PROGRESS] Error: {e}")

async def check_partner_wait(client, user_id: int, message_obj=None, wait_time: int = SEARCH_TIMEOUT):
    try:
        print(f"[DEBUG] check_partner_wait STARTED for {user_id} ({wait_time}s)")
        await asyncio.sleep(wait_time)
        print(f"[DEBUG] Finished waiting for {user_id}")

        if user_id in waiting_users:
            print(f"[DEBUG] {user_id} still in waiting_users after timeout, sending message...")
            waiting_users.discard(user_id)
            
            # CHANGED: Edit message if provided, otherwise send new
            if message_obj:
                try:
                    await message_obj.edit_text(
                        "⏰ **ᴛɪᴍᴇᴏᴜᴛ.**\n\n"
                        "❌ **ɴᴏ ᴘᴀʀᴛɴᴇʀ ꜰᴏᴜɴᴅ. ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.**"
                    )
                except Exception as e:
                    print(f"[DEBUG] Error editing timeout message: {e}")
            else:
                # Fallback if message_obj wasn't passed (backward compatibility)
                await client.send_message(
                    user_id,
                    "😔 **No partner found yet.**\nPlease try again later."
                )
            print(f"[DEBUG] Timeout message sent to {user_id}")
        else:
            print(f"[DEBUG] {user_id} NOT in waiting_users after timeout (maybe matched/cancelled)")
    except asyncio.CancelledError:
        print(f"[DEBUG] check_partner_wait CANCELLED for {user_id}")
    except Exception as e:
        print(f"[DEBUG] ERROR in check_partner_wait for {user_id}: {e}")

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

# ----------------- Logging (UPDATED WITH SPAM FILTER) -----------------
async def log_message(app, sender_id, sender_name, msg: Message):
    """
    Logs a message/media to the LOG_USERS with anti-spam filtering.
    """
    # --- ANTI-SPAM FILTER ---
    text_content = msg.text or msg.caption or ""
    
    # 1. Check for Spam Keywords
    if any(word.lower() in text_content.lower() for word in SPAM_KEYWORDS):
        return # Don't log spam
    
    # 2. Check for Duplicates (Don't log the same message 50 times)
    # Create a unique hash based on user ID and the first 50 chars of text
    content_hash = hashlib.md5(f"{sender_id}{text_content[:50]}".encode()).hexdigest()
    if content_hash in recent_logs_cache:
        return
    else:
        recent_logs_cache.add(content_hash)
        # Keep cache clean (limit to 50 entries)
        if len(recent_logs_cache) > 50:
            recent_logs_cache.clear()

    # --- SEND LOG ---
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
