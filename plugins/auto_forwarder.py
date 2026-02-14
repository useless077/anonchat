import asyncio
import logging
import os
import re
import json
from pyrogram import Client, filters
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

async def get_video_list(client: Client):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            pass

    logger.info("📥 Fetching videos from source channel...")

    video_ids = []
    async for msg in client.get_chat_history(FORWARDER_SOURCE_ID, limit=10000):
        if msg.photo or msg.video:
            video_ids.append(msg.id)

    video_ids.reverse()

    with open(CACHE_FILE, "w") as f:
        json.dump(video_ids, f)

    logger.info(f"✅ Cached {len(video_ids)} videos")
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

    video_ids = await get_video_list(client)

    if not video_ids:
        logger.error("❌ No videos found in source.")
        return

    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)

    while True:

        msg_obj = None
        is_live = False

        # ================= LIVE PRIORITY =================
        try:
            msg_obj = await asyncio.wait_for(post_queue.get(), timeout=1.0)
            is_live = True
            logger.info(f"🔴 LIVE Video {msg_obj.id}")
        except asyncio.TimeoutError:
            pass

        # ================= HISTORY =================
        if not msg_obj:
            if current_index >= len(video_ids):
                current_index = 0

            msg_id = video_ids[current_index]

            try:
                msg_obj = await client.get_messages(FORWARDER_SOURCE_ID, msg_id)
                logger.info(f"🟡 HISTORY {current_index+1}/{len(video_ids)}")
            except Exception as e:
                logger.error(f"❌ Fetch failed: {e}")
                current_index += 1
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

                # Remove dead groups automatically
                if "CHAT_WRITE_FORBIDDEN" in error_text or "PEER_ID_INVALID" in error_text:
                    await db.remove_group(chat_id)
                    logger.info(f"🗑 Removed dead group {chat_id}")

        # ================= UPDATE INDEX =================
        if not is_live:
            current_index += 1
            await db.save_forwarder_checkpoint(FORWARDER_SOURCE_ID, current_index)

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

    video_ids = await get_video_list(client)
    total = len(video_ids)

    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)
    pending = post_queue.qsize()

    percent = (current_index / total * 100) if total else 0

    text = (
        f"🔄 **Forwarder Status**\n\n"
        f"📂 Total Videos: `{total}`\n"
        f"📍 Current Index: `{current_index}`\n"
        f"📊 Progress: `{percent:.2f}%`\n"
        f"🔴 Live Queue: `{pending}`"
    )

    await message.reply(text)
