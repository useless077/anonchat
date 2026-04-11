import re
import os
import json
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db

logger = logging.getLogger(__name__)
CACHE_FILE = "video_list_cache.json"

# Global State
INDEX_LOCK = asyncio.Lock()
INDEX_CANCEL = False

# Regex to detect Telegram Links
LINK_REGEX = re.compile(r"(https?://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")


@Client.on_message(filters.private & (filters.forwarded | filters.text))
async def index_handler(client: Client, message: Message):
    """Handles forwarded messages or links to trigger indexing."""
    
    # 1. Parse Chat ID and Message ID
    chat_id = None
    last_msg_id = None

    # Case A: User sent a Link
    if message.text:
        match = LINK_REGEX.match(message.text)
        if not match:
            return  # Not a valid link, ignore

        raw_chat = match.group(4)
        last_msg_id = int(match.group(5))

        # Handle Private Links (c/12345) vs Public (@channel)
        if raw_chat.isnumeric():
            chat_id = int(f"-100{raw_chat}")
        else:
            chat_id = raw_chat

    # Case B: User Forwarded a Message
    elif message.forward_from_chat and message.forward_from_chat.type in [enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP]:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    # 2. Validate Access (Admin Check)
    try:
        # Test access to the channel
        await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"❌ **Access Error:** `{e}`\n\nMake sure bot is Admin in that channel.")

    # 3. Start Indexing
    status_msg = await message.reply(f"🔄 **Starting Index...**\nSource: `{chat_id}`\nFrom ID: `{last_msg_id}`")
    await run_indexing(client, status_msg, chat_id, last_msg_id)


@Client.on_message(filters.command("cancel_index") & filters.user(ADMIN_IDS))
async def cancel_index_cmd(client: Client, message: Message):
    """Cancels the current indexing process."""
    global INDEX_CANCEL
    INDEX_CANCEL = True
    await message.reply("🛑 **Indexing Cancelled.**")


async def run_indexing(client: Client, status_msg: Message, chat_id, start_id):
    """Main loop to fetch and save video IDs."""
    global INDEX_CANCEL
    INDEX_CANCEL = False
    
    async with INDEX_LOCK:
        # Load existing IDs to prevent duplicates
        video_ids = []
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    video_ids = json.load(f)
            except:
                pass

        count = 0
        skipped = 0
        
        # Iterate backwards from the starting message
        # reverse=False means Newest -> Oldest (Standard)
        try:
            async for msg in client.iter_messages(chat_id, offset_id=start_id, reverse=False):
                
                if INDEX_CANCEL:
                    await status_msg.edit(f"🛑 **Cancelled.**\nSaved: `{count}`")
                    return

                if msg.photo or msg.video:
                    if msg.id not in video_ids:
                        video_ids.append(msg.id)
                        count += 1
                    else:
                        skipped += 1

                # Update UI every 20 messages
                if count % 20 == 0 and count > 0:
                    await status_msg.edit(
                        f"📥 **Indexing...**\n"
                        f"Found: `{count}`\n"
                        f"Skipped: `{skipped}`\n\n"
                        f"⏳ Processing ID: `{msg.id}`..."
                    )
                    # Small save every 20 messages to be safe
                    try:
                        with open(CACHE_FILE, "w") as f:
                            json.dump(video_ids, f)
                    except:
                        pass

        except Exception as e:
            await status_msg.edit(f"❌ **Error:** {e}")
            return

        # Final Save
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(video_ids, f)
            
            # Update DB checkpoint so bot doesn't re-index from start
            await db.save_forwarder_checkpoint(chat_id, 0) 
            
            await status_msg.edit(
                f"✅ **Indexing Complete!**\n\n"
                f"Total Videos Saved: `{len(video_ids)}`\n"
                f"New Videos Added: `{count}`\n\n"
                f"💡 **Please restart the bot** to load these videos into the Auto Forwarder."
            )
        except Exception as e:
            logger.error(f"Final Save Error: {e}")
            await status_msg.edit(f"⚠️ Indexing finished but failed to save file: `{e}`")
