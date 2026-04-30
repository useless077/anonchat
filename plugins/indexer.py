import re
import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db

logger = logging.getLogger(__name__)

# Track active indexing users
ACTIVE_INDEXING = set()

# ✅ Improved Telegram link regex (supports all formats)
LINK_REGEX = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:c/)?([a-zA-Z0-9_]+|\d+)/(\d+)"
)


# ================================
# COMMAND HANDLER
# ================================

@Client.on_message(filters.command("index") & filters.user(ADMIN_IDS))
async def ask_link(client: Client, message: Message):

    chat_id = None
    start_msg_id = None

    text = message.text.strip() if message.text else None

    # ================= LINK PARSE =================
    if text:
        match = LINK_REGEX.search(text)

        if not match:
            return await message.reply("❌ Invalid Telegram link.")

        raw_chat = match.group(1)
        start_msg_id = int(match.group(2))

        if raw_chat.isnumeric():
            chat_id = int(f"-100{raw_chat}")
        else:
            chat_id = raw_chat

    # ================= FORWARDED =================
    elif message.forward_from_chat and message.forward_from_chat.type in [
        enums.ChatType.CHANNEL,
        enums.ChatType.SUPERGROUP,
    ]:
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
        start_msg_id = message.forward_from_message_id

    else:
        return await message.reply(
            "❌ Send a valid Telegram post link or forward a message."
        )

    # ================= ACCESS CHECK =================
    try:
        await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(
            f"❌ Access Error:\n`{e}`\n\nMake bot admin in source channel."
        )

    # ================= DUPLICATE TASK BLOCK =================
    if message.from_user.id in ACTIVE_INDEXING:
        return await message.reply("⚠️ Already indexing. Please wait.")

    ACTIVE_INDEXING.add(message.from_user.id)

    status_msg = await message.reply(
        f"🔄 **Indexing Started**\n\n"
        f"📡 Source: `{chat_id}`\n"
        f"📍 From ID: `{start_msg_id}`"
    )

    asyncio.create_task(run_indexing(client, status_msg, chat_id, start_msg_id))


# ================================
# INDEXING LOGIC
# ================================

async def run_indexing(client: Client, status_msg: Message, chat_id, start_id):

    user_id = status_msg.chat.id

    try:
        # Load existing IDs
        video_ids = await db.get_video_list_db(chat_id)
        existing_ids = set(video_ids)

        new_count = 0
        skipped = 0

        async for msg in client.get_chat_history(chat_id, offset_id=start_id):

            # Cancel support
            if user_id not in ACTIVE_INDEXING:
                await status_msg.edit("🛑 Indexing Cancelled.")
                return

            if msg.photo or msg.video:
                if msg.id not in existing_ids:
                    existing_ids.add(msg.id)
                    video_ids.append(msg.id)
                    new_count += 1
                else:
                    skipped += 1

            # UI update every 25
            if (new_count + skipped) % 25 == 0 and (new_count + skipped) != 0:
                try:
                    await status_msg.edit(
                        f"📥 **Indexing...**\n\n"
                        f"✅ New: `{new_count}`\n"
                        f"⏭ Skipped: `{skipped}`\n\n"
                        f"🔢 Last ID: `{msg.id}`"
                    )
                except Exception:
                    pass  # avoid flood/edit errors

    except Exception as e:
        logger.error(f"[INDEX ERROR] {e}")
        await status_msg.edit(f"❌ Error:\n`{e}`")
        return

    finally:
        ACTIVE_INDEXING.discard(user_id)

    # ================= FINAL SAVE =================
    try:
        # IMPORTANT: oldest → newest
        video_ids = sorted(set(video_ids))

        await db.save_video_list_db(chat_id, video_ids)

        # Reset checkpoint (start fresh)
        await db.save_forwarder_checkpoint(chat_id, 0)

        await status_msg.edit(
            f"✅ **Indexing Complete!**\n\n"
            f"📂 Total Videos: `{len(video_ids)}`\n"
            f"🆕 New Added: `{new_count}`\n\n"
            f"🔁 Forwarder restarted from beginning."
        )

    except Exception as e:
        logger.error(f"[SAVE ERROR] {e}")
        await status_msg.edit(f"⚠️ Save failed:\n`{e}`")
