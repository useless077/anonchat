import asyncio
import logging
import os
import re
import json
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
# REMOVED: ChatType (Not needed anymore as we use config list)
from config import FORWARDER_SOURCE_ID, FORWARDER_DEST_IDS, FORWARD_DELAY, AUTO_DELETE_DELAY, LOG_CHANNEL
from database.users import db 
from utils import check_bot_permissions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Queues and State ---
post_queue = asyncio.Queue()  # Priority queue for LIVE videos
processed_media_groups = set()

# --- Cache File for History Loop ---
CACHE_FILE = "video_list_cache.json"
INDEX_FILE = "last_index.txt"

# --- Custom Caption & Font Helper ---

def to_small_caps(text):
    mapping = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
        'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
        'q': 'q', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ',
        'x': 'x', 'y': 'y', 'z': 'z'
    }
    mapping.update({k.upper(): v for k, v in mapping.items()})

    # Protect @mentions and URLs
    pattern = r'(@\w+|https?://\S+|t\.me/\S+)'

    parts = re.split(pattern, text)
    result = ""

    for part in parts:
        if re.match(pattern, part):
            # Keep mentions and links unchanged
            result += part
        else:
            result += "".join(mapping.get(char, char) for char in part)

    return result

CUSTOM_CAPTION_TEXT = (
    "Just and me in your group for more videos\n\n"
    "Start me and get your partner now 😜❤️\n\n"
    "Join now guys @XtamilChat" 
)

async def delete_after_delay(client, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_ids)
        logger.info(f"🗑️ Deleted message(s) {message_ids} in {chat_id}")
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")

# --- VIDEO LIST MANAGEMENT ---
async def get_video_list(client: Client) -> list[int]:
    """
    Fetches ALL video IDs from source channel.
    Reverses them so they are in Chronological Order (Oldest -> Newest).
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                # Check if cache is older than 24 hours (optional, for now just use it)
                return data
        except:
            pass

    logger.info("📥 Fetching full video list from source channel (this may take a moment)...")
    video_ids = []
    # Fetch all messages (limit 0 means no limit, but API might limit. 10000 is safe).
    try:
        async for msg in client.get_chat_history(FORWARDER_SOURCE_ID, limit=10000):
            if msg.photo or msg.video:
                video_ids.append(msg.id)
        
        # Reverse to get Oldest -> Newest (1st Video -> Last Video)
        video_ids.reverse()
        
        with open(CACHE_FILE, 'w') as f:
            json.dump(video_ids, f)
        
        logger.info(f"✅ Fetched and cached {len(video_ids)} videos.")
        return video_ids
    except Exception as e:
        logger.error(f"❌ Error fetching video list: {e}")
        return []

def get_last_index() -> int:
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, 'r') as f:
                return int(f.read())
        except:
            return 0
    return 0

def save_last_index(index: int):
    with open(INDEX_FILE, 'w') as f:
        f.write(str(index))

async def forward_worker(client):
    logger.info("🚀 Auto Forwarder Worker (History Loop) Started")
    
    me = await client.get_me()
    bot_username = me.username if me.username else "TamilAnonymousChatBot"
    start_link = f"https://t.me/{bot_username}?start=start"
    final_caption = to_small_caps(CUSTOM_CAPTION_TEXT)

    # 1. Load the full list of video IDs
    video_ids = await get_video_list(client)
    if not video_ids:
        logger.error("❌ No videos found in source channel!")
        return

    # 2. Load current index (Resume where left off)
    current_index = get_last_index()
    if current_index >= len(video_ids):
        current_index = 0 # Reset if finished
        logger.info("🔄 Loop completed. Starting from Video #1 again.")
    else:
        logger.info(f"📍 Resuming from Video #{current_index + 1}")

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share me for more videos", url=start_link)]
    ])

    while True:
        msg_obj = None
        is_live = False

        # ---------------------------------------------------------
        # --- CHECK FOR LIVE UPDATES (PRIORITY) ---
        # ---------------------------------------------------------
        try:
            # Check if there are new live videos (timeout 1 second)
            msg_obj = await asyncio.wait_for(post_queue.get(), timeout=1.0)
            is_live = True
            logger.info(f"🔴 [LIVE INTERRUPT] Processing new video {msg_obj.id}...")
        except asyncio.TimeoutError:
            # No live videos, continue with History Loop
            pass

        # ---------------------------------------------------------
        # --- PROCESS VIDEO (Live or History) ---
        # ---------------------------------------------------------
        
        message_to_post = None

        if msg_obj:
            # It's a LIVE video
            message_to_post = msg_obj
        else:
            # It's HISTORY video (from the 1800 list)
            if current_index < len(video_ids):
                msg_id = video_ids[current_index]
                try:
                    # Fetch the message object by ID
                    msgs = await client.get_messages(FORWARDER_SOURCE_ID, msg_ids)
                    message_to_post = msgs[0] if isinstance(msgs, list) else msgs
                    logger.info(f"🟡 [HISTORY] Processing Video #{current_index + 1}/{len(video_ids)}...")
                except Exception as e:
                    logger.error(f"❌ Failed to fetch history msg {msg_id}: {e}")
                    # Skip this one and move next
                    current_index += 1
                    save_last_index(current_index)
                    continue
            else:
                # End of list, loop back to start
                logger.info("🔄 End of list. Refreshing cache and restarting loop...")
                current_index = 0
                save_last_index(current_index)
                # Optional: Refresh video list to catch new ones added to history
                video_ids = await get_video_list(client)
                continue

        if message_to_post:
            # --- POSTING LOGIC ---
            posted_count = 0
            
            for chat_id in FORWARDER_DEST_IDS:
                try:
                    chat_info = await client.get_chat(chat_id)
                    chat_title = chat_info.title
                except:
                    chat_title = str(chat_id)

                has_permissions = await check_bot_permissions(client, chat_id)
                
                if has_permissions:
                    try:
                        sent_msg = await message_to_post.copy(
                            chat_id=chat_id, 
                            caption=final_caption, 
                            reply_markup=reply_markup,
                            has_spoiler=True 
                        )
                        logger.info(f"✅ Sent to {chat_title}")
                        posted_count += 1
                        asyncio.create_task(delete_after_delay(client, chat_id, sent_msg.id, AUTO_DELETE_DELAY))
                    except Exception as e:
                        logger.error(f"❌ Failed to send to {chat_title}: {e}")
                else:
                    try:
                        warning_text = "Hola @admin I need invite users and delete permission to post videos here. You really missed the videos"
                        await client.send_message(chat_id, warning_text)
                        logger.info(f"⚠️ Sent permission warning to {chat_title}")
                    except Exception as e:
                        logger.error(f"❌ Could not send warning to {chat_title}: {e}")

            # --- UPDATE STATE ---
            if is_live:
                # If it was a live video, DO NOT update current_index.
                # We stay at the same spot in history for the next run.
                logger.info(f"✅ [LIVE] Posted. History index remains at {current_index}.")
            else:
                # If it was history, increment index
                current_index += 1
                save_last_index(current_index)
                if current_index >= len(video_ids):
                    logger.info("🏁 History Cycle Complete.")
                    current_index = 0 # Reset for next loop
                    save_last_index(current_index)

            # --- WAIT ---
            logger.info(f"⏳ Waiting {FORWARD_DELAY // 60} minutes...")
            await asyncio.sleep(FORWARD_DELAY)


# Keep catch_media simple - just adds to queue
@Client.on_message(filters.chat(FORWARDER_SOURCE_ID) & (filters.photo | filters.video))
async def catch_media(client, message):
    # We don't need complex checks here anymore.
    # The worker handles the logic.
    media_group_id = message.media_group_id

    if not media_group_id:
        await post_queue.put(message)
        logger.info(f"➕ [LIVE] Added {message.id} to queue.")
        return

    if media_group_id in processed_media_groups:
        return

    try:
        processed_media_groups.add(media_group_id)
        media_messages = await client.get_media_group(message.chat.id, message.id)
        for msg in media_messages:
            await post_queue.put(msg)
            logger.info(f"➕ [LIVE] Added {msg.id} (album) to queue.")
    except Exception as e:
        logger.error(f"Error processing live media group: {e}")
        if media_group_id in processed_media_groups:
            processed_media_groups.remove(media_group_id)
