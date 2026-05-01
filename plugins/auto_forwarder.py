import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import (
    FORWARDER_DEST_IDS,
    FORWARD_DELAY,
    AUTO_DELETE_DELAY,
    ADMIN_IDS,
    LOG_USERS
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

    result = ""
    for part in parts:
        if re.match(pattern, part):
            result += part
        else:
            result += "".join(mapping.get(c, c) for c in part)

    return result


CUSTOM_CAPTION_TEXT = (
    "🔥 New Video Uploaded 🔥\n\n"
    "Just add me in your group for more videos\n\n"
    "Start me and get your partner now 😜❤️\n\n"
    "📍 ᴊᴏɪɴ ɴᴏᴡ @XtamilChat" 
)

processed_media_groups = {}


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
# GET ALL SOURCES
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
# FORWARD WORKER
# ================================
async def forward_worker(client: Client):

    me = await client.get_me()
    bot_username = me.username or "AnonymousBot"
    start_link = f"https://t.me/{bot_username}?start=start"

    caption = to_small_caps(CUSTOM_CAPTION_TEXT)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share me for more videos", url=start_link)]
    ])

    while True:

        sources = await get_all_sources()

        if not sources:
            print("[FORWARDER] No sources found")
            await asyncio.sleep(5)
            continue

        for source_id in sources:

            video_ids = await db.get_video_list_db(source_id)

            if not video_ids:
                continue

            video_ids = sorted(video_ids)

            current_index = await db.get_forwarder_checkpoint(source_id)

            if current_index >= len(video_ids):
                current_index = 0

            msg_id = video_ids[current_index]

            try:
                msg_obj = await client.get_messages(source_id, msg_id)
            except Exception as e:
                print(f"[FETCH ERROR] {source_id} → {e}")
                await db.save_forwarder_checkpoint(source_id, current_index + 1)
                continue

            # ================= SEND TO GROUPS =================
            for chat_id in FORWARDER_DEST_IDS:

                if not await check_bot_permissions(client, chat_id):
                    print(f"[SKIP] No permission in {chat_id}")
                    continue

                try:
                    sent = await msg_obj.copy(
                        chat_id=chat_id,
                        caption=caption,
                        reply_markup=reply_markup,
                        has_spoiler=True
                    )

                    asyncio.create_task(delete_after_delay(client, chat_id, sent.id))

                    # LOG
                    try:
                        await client.send_message(
                            LOG_USERS,
                            f"📤 `{source_id}` → `{chat_id}` | Msg `{sent.id}`",
                            parse_mode=enums.ParseMode.MARKDOWN
                        )
                    except Exception as log_error:
                        print(f"[LOG ERROR] {log_error}")

                except Exception as e:
                    print(f"[FORWARD ERROR] {chat_id} → {e}")
                    continue

            current_index += 1
            await db.save_forwarder_checkpoint(source_id, current_index)

            await asyncio.sleep(FORWARD_DELAY)

        await asyncio.sleep(1)


# ================================
# STATUS COMMAND
# ================================
@Client.on_message(filters.command("fstatus") & filters.user(ADMIN_IDS))
async def file_status(client: Client, message: Message):

    sources = await get_all_sources()

    text = "🔄 **Forwarder Status**\n\n"

    for source_id in sources:
        video_ids = await db.get_video_list_db(source_id)
        total = len(video_ids)
        current = await db.get_forwarder_checkpoint(source_id)
        percent = (current / total * 100) if total else 0

        text += (
            f"📡 `{source_id}`\n"
            f"📂 Total: `{total}`\n"
            f"📍 Index: `{current}`\n"
            f"📊 `{percent:.2f}%`\n\n"
        )

    await message.reply(text, parse_mode=enums.ParseMode.MARKDOWN)
