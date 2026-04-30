import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import (
    FORWARDER_SOURCE_ID,
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
    "Just add me in your group for more videos\n\n"
    "Start me and get your partner now 😜❤️\n\n"
    "Join now guys @XtamilChat"
)

# ================================
# CACHE
# ================================
processed_media_groups = set()


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
# FORWARD WORKER
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

    video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)

    if not video_ids:
        print("[FORWARDER] No videos found in DB")
        return

    while True:

        if current_index >= len(video_ids):
            current_index = 0

        msg_id = video_ids[current_index]

        try:
            msg_obj = await client.get_messages(FORWARDER_SOURCE_ID, msg_id)
        except Exception as e:
            print(f"[FETCH ERROR] {e}")
            current_index += 1
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

                # auto delete
                asyncio.create_task(delete_after_delay(client, chat_id, sent.id))

                # ================= LOG =================
                try:
                    await client.send_message(
                        LOG_USERS,
                        f"📤 Sent to `{chat_id}` | Msg `{sent.id}`",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                except Exception as log_error:
                    print(f"[LOG ERROR] {log_error}")

            except Exception as e:
                print(f"[FORWARD ERROR] {chat_id} → {e}")
                continue

        current_index += 1
        await db.save_forwarder_checkpoint(FORWARDER_SOURCE_ID, current_index)

        await asyncio.sleep(FORWARD_DELAY)


# ================================
# MEDIA CATCHER (APPEND)
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
# STATUS COMMAND
# ================================
@Client.on_message(filters.command("fstatus") & filters.user(ADMIN_IDS))
async def file_status(client: Client, message: Message):

    video_ids = await db.get_video_list_db(FORWARDER_SOURCE_ID)
    total = len(video_ids)
    current_index = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)

    percent = (current_index / total * 100) if total else 0

    await message.reply(
        f"🔄 **Forwarder Status**\n\n"
        f"📂 Total Videos: `{total}`\n"
        f"📍 Current Index: `{current_index}`\n"
        f"📊 Progress: `{percent:.2f}%`",
        parse_mode=enums.ParseMode.MARKDOWN
    )
