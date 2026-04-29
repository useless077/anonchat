import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import FORWARDER_SOURCE_ID, FORWARD_DELAY, AUTO_DELETE_DELAY, ADMIN_IDS
from database.users import db
from utils import check_bot_permissions

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
# MEDIA GROUP TRACKING
# ================================

processed_media_groups = set()

# ================================
# VIDEO LIST FETCH
# ================================

async def get_video_list(client: Client, force_refresh=False):
    if not force_refresh:
        try:
            video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
            if video_ids:
                return video_ids
        except:
            pass

    try:
        video_ids = []
        async for msg in client.get_chat_history(FORWARDER_SOURCE_ID, limit=10000):
            if msg.photo or msg.video:
                video_ids.append(msg.id)

        video_ids.reverse()

        await db.save_video_list_db(FORWARDER_SOURCE_ID, video_ids)
        return video_ids

    except Exception as e:
        print(f"[FORWARDER] Fetch error: {e}")
        return []


# ================================
# AUTO DELETE
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

    global processed_media_groups

    try:
        processed_media_groups = await db.get_media_groups_db()
    except:
        processed_media_groups = set()

    me = await client.get_me()
    bot_username = me.username or "AnonymousBot"
    start_link = f"https://t.me/{bot_username}?start=start"

    caption = to_small_caps(CUSTOM_CAPTION_TEXT)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share me for more videos", url=start_link)]
    ])

    video_ids = await get_video_list(client)
    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)

    refresh_counter = 0

    while True:

        # Refresh list periodically (important for new videos)
        refresh_counter += 1
        if refresh_counter >= 10:
            try:
                video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
                refresh_counter = 0
            except:
                pass

        if not video_ids:
            await asyncio.sleep(5)
            continue

        if current_index >= len(video_ids):
            current_index = 0

        msg_id = video_ids[current_index]

        try:
            msg_obj = await client.get_messages(FORWARDER_SOURCE_ID, msg_id)
        except:
            current_index += 1
            continue

        groups = await db.get_all_groups()

        for group in groups:
            chat_id = group["_id"]

            if not await check_bot_permissions(client, chat_id):
                continue

            try:
                sent = await msg_obj.copy(
                    chat_id=chat_id,
                    caption=caption,
                    reply_markup=reply_markup,
                    has_spoiler=True
                )

                asyncio.create_task(delete_after_delay(client, chat_id, sent.id))

            except:
                continue

        current_index += 1
        await db.save_forwarder_checkpoint(FORWARDER_SOURCE_ID, current_index)

        await asyncio.sleep(FORWARD_DELAY)


# ================================
# MEDIA CATCHER (APPEND MODE)
# ================================

@Client.on_message(filters.chat(FORWARDER_SOURCE_ID) & (filters.photo | filters.video), group=5)
async def catch_media(client, message):

    media_group_id = message.media_group_id

    if media_group_id:

        if media_group_id in processed_media_groups:
            return

        processed_media_groups.add(media_group_id)
        asyncio.create_task(db.add_media_group_db(media_group_id))

        try:
            media_messages = await client.get_media_group(message.chat.id, message.id)

            for msg in media_messages:
                if msg.photo or msg.video:
                    await db.append_video_id(FORWARDER_SOURCE_ID, msg.id)

        except:
            processed_media_groups.discard(media_group_id)

    else:
        await db.append_video_id(FORWARDER_SOURCE_ID, message.id)


# ================================
# ADMIN COMMANDS
# ================================

@Client.on_message(filters.command("fstatus") & filters.user(ADMIN_IDS))
async def file_status(client: Client, message: Message):

    video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
    total = len(video_ids)
    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)

    percent = (current_index / total * 100) if total else 0

    text = (
        f"🔄 **Forwarder Status**\n\n"
        f"📂 Total Videos: `{total}`\n"
        f"📍 Current Index: `{current_index}`\n"
        f"📊 Progress: `{percent:.2f}%`\n\n"
        f"💡 `/refresh_cache` to reload from source."
    )

    await message.reply(text, parse_mode=enums.ParseMode.MARKDOWN)


@Client.on_message(filters.command("refresh_cache") & filters.user(ADMIN_IDS))
async def refresh_cache_cmd(client: Client, message: Message):

    msg = await message.reply("🔄 Refreshing cache...")

    await get_video_list(client, force_refresh=True)

    await msg.edit("✅ Cache refreshed successfully!")
