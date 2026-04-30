import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import ADMIN_IDS
from database.users import db

logger = logging.getLogger(__name__)

INDEXING = set()

# Telegram link regex
LINK_REGEX = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:c/)?([a-zA-Z0-9_]+|\d+)/(\d+)"
)


# ================================
# COMMAND
# ================================
@Client.on_message(filters.command("index") & filters.user(ADMIN_IDS))
async def index_handler(client: Client, message: Message):

    if len(message.command) < 2:
        return await message.reply(
            "❌ Send link like:\n/index https://t.me/channel/123"
        )

    text = message.command[1].strip()
    match = LINK_REGEX.search(text)

    if not match:
        return await message.reply("❌ Invalid Telegram link.")

    raw_chat = match.group(1)
    last_msg_id = int(match.group(2))

    # convert chat id
    if raw_chat.isnumeric():
        chat_id = int(f"-100{raw_chat}")
    else:
        chat_id = raw_chat

    # access check
    try:
        await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"❌ Access Error:\n`{e}`")

    # prevent multiple runs
    if message.from_user.id in INDEXING:
        return await message.reply("⚠️ Already indexing...")

    INDEXING.add(message.from_user.id)

    status = await message.reply(
        f"🔄 Indexing started\n\n"
        f"📡 Chat: `{chat_id}`\n"
        f"📍 Last ID: `{last_msg_id}`"
    )

    asyncio.create_task(run_index(client, status, chat_id, last_msg_id))


# ================================
# INDEX LOGIC
# ================================
async def run_index(client, status_msg, chat_id, last_msg_id):

    user_id = status_msg.chat.id

    total = 0
    duplicates = 0
    errors = 0

    try:
        for msg_id in range(1, last_msg_id + 1):

            # cancel support
            if user_id not in INDEXING:
                await status_msg.edit("🛑 Cancelled")
                return

            try:
                msg = await client.get_messages(chat_id, msg_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            except:
                errors += 1
                continue

            if not msg or msg.empty:
                continue

            media = msg.video or msg.photo or msg.document

            if media:
                try:
                    # ✅ DB handles duplicate automatically
                    added = await db.append_video_id(chat_id, msg.id)

                    if added:
                        total += 1
                    else:
                        duplicates += 1

                except Exception as e:
                    errors += 1
                    logger.error(f"Append error: {e}")

            # progress update
            if msg_id % 50 == 0:
                try:
                    await status_msg.edit(
                        f"📥 Indexing...\n\n"
                        f"📊 Processed: `{msg_id}`\n"
                        f"✅ Saved: `{total}`\n"
                        f"⏭ Duplicates: `{duplicates}`\n"
                        f"⚠️ Errors: `{errors}`"
                    )
                except:
                    pass

            await asyncio.sleep(0.05)

    except Exception as e:
        logger.error(e)
        await status_msg.edit(f"❌ Error:\n`{e}`")
        return

    finally:
        INDEXING.discard(user_id)

    # final result
    try:
        video_ids = await db.get_video_list_db(chat_id)

        await status_msg.edit(
            f"✅ Index Completed\n\n"
            f"📡 Source: `{chat_id}`\n"
            f"📂 Total Stored: `{len(video_ids)}`\n"
            f"🆕 New Added: `{total}`\n"
            f"⏭ Duplicates: `{duplicates}`"
        )

    except Exception as e:
        await status_msg.edit(f"⚠️ Final Error:\n`{e}`")


# ================================
# STOP COMMAND
# ================================
@Client.on_message(filters.command("stop") & filters.user(ADMIN_IDS))
async def stop_index(client, message):
    INDEXING.discard(message.from_user.id)
    await message.reply("🛑 Indexing stopped.")
