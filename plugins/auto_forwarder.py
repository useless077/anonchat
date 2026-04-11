import asyncio
import logging
import re
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
# We will load this from DB in the worker
processed_media_groups = set() 

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
# VIDEO LIST FETCH (MONGODB)
# ================================

async def get_video_list(client: Client, force_refresh=False):
    # 1. Try to load from DB first (Fast)
    if not force_refresh:
        video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
        if video_ids:
            logger.info(f"📂 Loaded {len(video_ids)} videos from MongoDB Cache.")
            return video_ids

    # 2. If not in DB or force refresh, fetch from Telegram
    logger.info("📥 Fetching videos from source channel... (This might take a moment)")
    video_ids = []
    
    try:
        async for msg in client.get_chat_history(FORWARDER_SOURCE_ID, limit=10000):
            if msg.photo or msg.video:
                video_ids.append(msg.id)
                
        video_ids.reverse()
        
        # 3. Save to DB
        await db.save_video_list_db(FORWARDER_SOURCE_ID, video_ids)
        
    except Exception as e:
        logger.error(f"❌ Error fetching history: {e}")
        logger.warning("⚠️ TIP: Make the bot an ADMIN in the source channel.")
        return []

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

    # Initialize processed_media_groups from DB to prevent reposts after restart
    global processed_media_groups
    processed_media_groups = await db.get_media_groups_db()
    logger.info(f"🧠 Loaded {len(processed_media_groups)} processed groups from DB.")

    me = await client.get_me()
    bot_username = me.username or "AnonymousBot"
    start_link = f"https://t.me/{bot_username}?start=start"

    caption = to_small_caps(CUSTOM_CAPTION_TEXT)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share me for more videos", url=start_link)]
    ])

    # Load video list from DB (or fetch if empty)
    video_ids = await get_video_list(client)

    # Get current checkpoint
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
            if not video_ids:
                # No history available (Bot not admin or channel empty)
                await asyncio.sleep(5)
                continue

            if current_index >= len(video_ids):
                current_index = 0 # Loop back to start

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
        # Single media (not an album), put in queue immediately
        await post_queue.put(message)
        return

    # Album logic
    if media_group_id in processed_media_groups:
        return # Already processed this album

    # New album found
    processed_media_groups.add(media_group_id)
    
    # Save to DB asynchronously so we remember it after restart
    asyncio.create_task(db.add_media_group_db(media_group_id))

    try:
        # Fetch all messages in this album
        media_messages = await client.get_media_group(message.chat.id, message.id)
        for msg in media_messages:
            await post_queue.put(msg)
    except:
        # If fetching fails, remove from local set so we can try again later
        if media_group_id in processed_media_groups:
            processed_media_groups.remove(media_group_id)

# ================================
# ADMIN COMMANDS
# ================================

# ================================
# ADMIN COMMANDS
# ================================

@Client.on_message(filters.command("fstatus") & filters.user(ADMIN_IDS))
async def file_status(client: Client, message: Message):
    video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
    total = len(video_ids)
    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)
    pending = post_queue.qsize()

    percent = (current_index / total * 100) if total else 0

    text = (
        f"🔄 **Forwarder Status**\n\n"
        f"📂 Total Videos (DB): `{total}`\n"
        f"📍 Current Index: `{current_index}`\n"
        f"📊 Progress: `{percent:.2f}%`\n"
        f"🔴 Live Queue: `{pending}`\n\n"
        f"💡 `/refresh_cache` to fetch from channel."
    )

    # FIXED: Changed "markdown" to enums.ParseMode.MARKDOWN
    await message.reply(text, parse_mode=enums.ParseMode.MARKDOWN)

@Client.on_message(filters.command("refresh_cache") & filters.user(ADMIN_IDS))
async def refresh_cache_cmd(client: Message):
    msg = await message.reply("🔄 Refreshing video list from channel... please wait.")
    await get_video_list(client, force_refresh=True)
    # FIXED: Changed .edit() text only, removed parse_mode to avoid issues, or use correct enum
    await msg.edit("✅ Cache Refreshed & Saved to Database!")
