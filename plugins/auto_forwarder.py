import asyncio
import re
import aiohttp

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import (
    FORWARDER_DEST_IDS,
    FORWARD_DELAY,
    AUTO_DELETE_DELAY,
    ADMIN_IDS,
    LOG_USERS,
    BOT_USERNAME,
    TERABOX_API,
    ENABLE_TERABOX
)

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

    return "".join(
        part if re.match(pattern, part)
        else "".join(mapping.get(c, c) for c in part)
        for part in parts
    )


# ================================
# CAPTION
# ================================
CUSTOM_CAPTION_TEXT = (
    "🔥 New Video Uploaded 🔥\n"
    "⚡ Fast Download Available ⚡\n"
    "👇 Click Below Button 👇\n\n"
    "💥 <b>DOWNLOAD NOW</b> 💥\n\n"
    "📍 ᴊᴏɪɴ ɴᴏᴡ @XtamilChat"
)


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
# SOURCES
# ================================
async def get_all_sources():
    sources = []
    cursor = db.cache_col.find({"_id": {"$regex": "^video_list_"}})

    async for doc in cursor:
        source_id = doc["_id"].replace("video_list_", "")
        try:
            source_id = int(source_id)
        except:
            pass
        sources.append(source_id)

    return sources


# ================================
# GET LINK
# ================================
async def get_download_link(msg_obj):
    if msg_obj and msg_obj.caption:
        urls = re.findall(r'(https?://\S+)', msg_obj.caption)
        if urls:
            return urls[0]
    return None


# ================================
# SHORTLINK (TERABOX ONLY)
# ================================
async def shorten_with_terabox(url):
    try:
        api = f"https://teraboxurl.in/api?api={TERABOX_API}&url={url}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api) as r:
                data = await r.json()
                return data.get("shortenedUrl")
    except:
        return None


async def shorten_url(url):
    if not ENABLE_TERABOX:
        return url

    res = await shorten_with_terabox(url)
    if res:
        return res

    return url


# ================================
# FORWARDER WORKER
# ================================
async def forward_worker(client: Client):

    me = await client.get_me()
    bot_username = BOT_USERNAME or me.username
    start_link = f"https://t.me/{bot_username}?start=start"

    while True:

        sources = await get_all_sources()
        if not sources:
            await asyncio.sleep(5)
            continue

        for source_id in sources:

            video_ids = await db.get_video_list_db(source_id)
            if not video_ids:
                continue

            video_ids = sorted(video_ids)
            index = await db.get_forwarder_checkpoint(source_id)

            if index >= len(video_ids):
                index = 0

            msg_id = video_ids[index]

            # ================= SAFE MESSAGE FETCH =================
            try:
                msg_obj = await client.get_messages(source_id, msg_id)
            except Exception as e:
                print(f"[GET MESSAGE ERROR] {e}")
                await db.save_forwarder_checkpoint(source_id, index + 1)
                continue

            if not msg_obj:
                await db.save_forwarder_checkpoint(source_id, index + 1)
                continue

            # ================= LINK EXTRACTION =================
            link = await get_download_link(msg_obj)

            if not link:
                await db.save_forwarder_checkpoint(source_id, index + 1)
                continue

            short_link = await shorten_url(link)

            caption = (
                CUSTOM_CAPTION_TEXT +
                f"\n\n🔗 Direct Link: {short_link}"
            )

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬇️ 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗 𝗡𝗢𝗪 🔥", url=short_link)],
                [InlineKeyboardButton("🔗 Share", url=start_link)]
            ])

            # ================= SEND TO GROUPS =================
            for chat_id in FORWARDER_DEST_IDS:

                if not await check_bot_permissions(client, chat_id):
                    continue

                try:
                    sent = await msg_obj.copy(
                        chat_id=chat_id,
                        caption=caption,
                        reply_markup=markup,
                        has_spoiler=True
                    )

                    if sent:
                        asyncio.create_task(
                            delete_after_delay(client, chat_id, sent.id)
                        )

                except Exception as e:
                    print(f"[FORWARD ERROR] {e}")

            index += 1
            await db.save_forwarder_checkpoint(source_id, index)

            await asyncio.sleep(FORWARD_DELAY)

        await asyncio.sleep(1)


# ================================
# STATUS COMMAND
# ================================
@Client.on_message(filters.command("fstatus") & filters.user(ADMIN_IDS))
async def file_status(client: Client, message: Message):

    sources = await get_all_sources()
    text = "🔄 Forwarder Status\n\n"

    for source_id in sources:
        video_ids = await db.get_video_list_db(source_id)
        total = len(video_ids)
        current = await db.get_forwarder_checkpoint(source_id)

        percent = (current / total * 100) if total else 0

        text += (
            f"📡 {source_id}\n"
            f"Total: {total}\n"
            f"Index: {current}\n"
            f"{percent:.2f}%\n\n"
        )

    await message.reply(text)
