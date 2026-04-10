import asyncio
import logging
import os
import re
import json
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import FORWARDER_SOURCE_ID, FORWARD_DELAY, AUTO_DELETE_DELAY, ADMIN_IDS
from database.users import db
from utils import check_bot_permissions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================================
# QUEUE SYSTEM
# ================================

post_queue = asyncio.Queue()
processed_media_groups = set()

CACHE_FILE = "video_list_cache.json"

# ================================
# SMALL CAPS
# ================================

def to_small_caps(text):
    mapping = {
        'a': 'ᴀ','b': 'ʙ','c': 'ᴄ','d': 'ᴅ','e': 'ᴇ','f': 'ғ','g': 'ɢ','h': 'ʜ',
        'i': 'ɪ','j': 'ᴊ','k': 'ᴋ','l': 'ʟ','m': 'ᴍ','n': 'ɴ','o': 'ᴏ','p': 'ᴘ',
        'r': 'ʀ','t': 'ᴛ','u': 'ᴜ','v': 'ᴠ','w': 'ᴡ'
    }
    mapping.update({k.upper(): v for k, v in mapping.items()})

    pattern = r'(@\w+|https?://\S+|t\.me/\S+)'
    parts = re.split(pattern, text)

    result = ""
    for part in parts:
        if re.match(pattern, part):
            result += part
        else:
            result += "".join(mapping.get(c, c) for c in part)

    return result


CUSTOM_CAPTION_TEXT = (
    "Just add me in your group for more videos\n\n"
    "Start me and get your partner now 😜❤️\n\n"
    "Join now guys @XtamilChat"
)

# ================================
# VIDEO LIST FETCH
# ================================

async def get_video_list(client: Client, force_refresh=False):
    # 1. Try to use existing cache if available and not forcing refresh
    if os.path.exists(CACHE_FILE) and not force_refresh:
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                if data: 
                    logger.info("📂 Using cached video list.")
                    return data
        except Exception:
            pass 

    logger.info("📥 Attempting to fetch videos from source channel...")
    video_ids = []
    
    try:
        # Note: Bot MUST be Admin in source channel for this to work
        async for msg in client.get_chat_history(FORWARDER_SOURCE_ID, limit=300):
            if msg.photo or msg.video:
                video_ids.append(msg.id)
    except Exception as e:
        logger.error(f"⚠️ Could not fetch history (Bot might not be Admin in source): {e}")
        logger.warning("⚠️ Switching to Live-Only mode.")
        return []

    # Reverse so index 0 is the oldest video (1st video)
    video_ids.reverse()

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(video_ids, f)
    except Exception as e:
        logger.warning(f"Could not write cache file: {e}")

    logger.info(f"✅ Successfully cached {len(video_ids)} videos.")
    return video_ids


# ================================
# DELETE AFTER DELAY
# ================================

async def delete_after_delay(client, chat_id, message_id):
    await asyncio.sleep(AUTO_DELETE_DELAY)
    try:
        await client.delete_messages(chat_id, message_id)
    except:
        pass


# ================================
# MAIN WORKER
# ================================

async def forward_worker(client: Client):
    logger.info("🚀 Forward Worker Started")

    me = await client.get_me()
    bot_username = me.username or "AnonymousBot"
    start_link = f"https://t.me/{bot_username}?start=start"

    caption = to_small_caps(CUSTOM_CAPTION_TEXT)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share me for more videos", url=start_link)]
    ])

    # Fetch history list (returns [] if bot not admin)
    video_ids = await get_video_list(client)

    # Load the last saved position
    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)

    while True:
        msg_obj = None
        is_live = False

        # ================= LIVE PRIORITY =================
        try:
            msg_obj = await asyncio.wait_for(post_queue.get(), timeout=1.0)
            is_live = True
            logger.info(f"🔴 [LIVE] Forwarding video ID: {msg_obj.id}")
        except asyncio.TimeoutError:
            pass

        # ================= HISTORY =================
        if not msg_obj:
            # If we have no history data, just wait for live posts
            if not video_ids:
                await asyncio.sleep(2)
                continue

            # Cycle Logic: Restart from 0 if end reached
            if current_index >= len(video_ids):
                logger.info("🔄 End of history reached. Restarting from 1st video.")
                current_index = 0

            msg_id = video_ids[current_index]

            try:
                msg_obj = await client.get_messages(FORWARDER_SOURCE_ID, msg_id)
                logger.info(f"🟡 [HISTORY] Forwarding index {current_index+1}/{len(video_ids)}")
            except Exception as e:
                logger.error(f"❌ Fetch failed: {e}")
                # Skip this broken video
                current_index += 1
                await db.save_forwarder_checkpoint(FORWARDER_SOURCE_ID, current_index)
                continue

        if not msg_obj:
            continue

        # ================= SEND TO ALL GROUPS =================
        groups = await db.get_all_groups()

        for group in groups:
            chat_id = group["_id"]

            has_permission = await check_bot_permissions(client, chat_id)

            if not has_permission:
                logger.warning(f"⚠ No permission in {chat_id}")
                continue

            try:
                sent = await msg_obj.copy(
                    chat_id=chat_id,
                    caption=caption,
                    reply_markup=reply_markup,
                    has_spoiler=True
                )

                asyncio.create_task(delete_after_delay(client, chat_id, sent.id))
                logger.info(f"✅ Sent to {chat_id}")

            except Exception as e:
                error_text = str(e).upper()
                logger.error(f"❌ Send failed {chat_id}: {error_text}")

                if "CHAT_WRITE_FORBIDDEN" in error_text or "PEER_ID_INVALID" in error_text:
                    await db.remove_group(chat_id)
                    logger.info(f"🗑 Removed dead group {chat_id}")

        # ================= UPDATE INDEX =================
        # Only increment if it was a history video
        if not is_live:
            current_index += 1
            await db.save_forwarder_checkpoint(FORWARDER_SOURCE_ID, current_index)
        else:
            logger.info("⏸️ History paused due to Live video.")

        logger.info(f"⏳ Sleeping {FORWARD_DELAY} seconds")
        await asyncio.sleep(FORWARD_DELAY)


# ================================
# LIVE MEDIA CATCHER
# ================================

@Client.on_message(filters.chat(FORWARDER_SOURCE_ID) & (filters.photo | filters.video))
async def catch_media(client, message):

    media_group_id = message.media_group_id

    if not media_group_id:
        await post_queue.put(message)
        return

    if media_group_id in processed_media_groups:
        return

    processed_media_groups.add(media_group_id)

    try:
        media_messages = await client.get_media_group(message.chat.id, message.id)
        for msg in media_messages:
            await post_queue.put(msg)
    except:
        processed_media_groups.remove(media_group_id)


# ================================
# ADMIN STATUS COMMAND
# ================================

@Client.on_message(filters.command("fstatus") & filters.user(ADMIN_IDS))
async def file_status(client: Client, message: Message):
    # Force refresh=False to use cache for speed
    video_ids = await get_video_list(client, force_refresh=False)
    total = len(video_ids)

    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)
    pending = post_queue.qsize()

    percent = (current_index / total * 100) if total else 0

    text = (
        f"🔄 **Forwarder Status**\n\n"
        f"📂 Total Videos (Cached): `{total}`\n"
        f"📍 Current Index: `{current_index}`\n"
        f"📊 Progress: `{percent:.2f}%`\n"
        f"🔴 Live Queue: `{pending}`\n\n"
        f"💡 If total is 0, make the bot an **Admin** in the source channel."
    )

    # FIXED: Use enums.ParseMode.MARKDOWN instead of string "markdown"
    await message.reply(text, parse_mode=enums.ParseMode.MARKDOWN)

@Client.on_message(filters.command("refresh_cache") & filters.user(ADMIN_IDS))
async def refresh_cache_cmd(client, message):
    msg = await message.reply("🔄 Refreshing video list... please wait.")
    await get_video_list(client, force_refresh=True)
    
    # FIXED: Wrap edit in try-except to avoid MessageNotModified error
    try:
        await msg.edit("✅ Cache Refreshed!")
    except Exception:
        pass
