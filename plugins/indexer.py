# plugins/indexer.py

import re
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import ADMIN_IDS, LOG_CHANNEL
from database.users import db

logger = logging.getLogger(__name__)

# Global set to track active indexing tasks
ACTIVE_INDEXING = set()

LINK_REGEX = re.compile(r"(https?://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")


@Client.on_message(filters.command("index"))
async def ask_link(client: Client, message: Message):
    """Handles forwarded messages or links to trigger indexing."""
    
    # 1. Check if indexing is already running for this user
    if message.from_user.id in ACTIVE_INDEXING:
        return await message.reply("⚠️ You are already indexing a channel. Please wait.")
    
    # 2. Parse Chat ID and Message ID
    chat_id = None
    last_msg_id = None

    if message.text:
        match = LINK_REGEX.match(message.text)
        if not match:
            return # Not a valid link, ignore

        raw_chat = match.group(4)
        last_msg_id = int(match.group(5))

        if raw_chat.isnumeric():
            chat_id = int(f"-100{raw_chat}")
        else:
            chat_id = raw_chat

    elif message.forward_from_chat and message.forward_from_chat.type in [enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP]:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    # 3. Validate Access (Admin Check)
    try:
        await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"❌ **Access Error:** `{e}`\n\nMake sure bot is Admin in that channel.")

    # 4. Start Indexing (Non-Blocking)
    ACTIVE_INDEXING.add(message.from_user.id)
    status_msg = await message.reply(f"🔄 **Starting Index...**\nSource: `{chat_id}`\nFrom ID: `{last_msg_id}`")
    
    # Run the heavy logic in a separate task so other commands work
    asyncio.create_task(run_indexing(client, status_msg, chat_id, last_msg_id, message.from_user.id))


async def run_indexing(pyro_client: Client, status_msg: Message, chat_id, start_id, user_id):
    """Main loop to fetch and save video IDs to MongoDB."""
    global ACTIVE_INDEXING
    
    try:
        # Load existing IDs from MongoDB to prevent duplicates
        video_ids = await db.get_video_list_db(chat_id)
        existing_ids_set = set(video_ids)
        
        new_videos_count = 0
        skipped_count = 0
        
        # Loop backwards from the starting message
        # Note: We offset by 1 to ensure we process the starting message itself too if needed
        current_id = start_id - 1 if start_id else start_id
        
        async for msg in pyro_client.get_chat_history(chat_id, offset_id=current_id):
            if user_id not in ACTIVE_INDEXING:
                break # User cancelled
                
            if msg.photo or msg.video:
                if msg.id not in existing_ids_set:
                    existing_ids_set.add(msg.id)
                    video_ids.append(msg.id)
                    new_videos_count += 1
                else:
                    skipped_count += 1

            # Update UI every 20 messages (with FloodWait protection)
            if (new_videos_count + skipped_count) % 20 == 0 and (new_videos_count + skipped_count) > 0:
                try:
                    await status_msg.edit(
                        f"📦 **Indexing...**\n"
                        f"New: `{new_videos_count}` | Skipped: `{skipped_count}`\n"
                        f"⏳ Current: `{msg.id}`"
                    )
                except FloodWait as e:
                    # If we hit a limit, just pause, don't crash
                    await asyncio.sleep(e.value)
                    # Try updating again after wait
                    await status_msg.edit(f"⚠️ Rate Limited. Sleeping... ({e.value}s)")

        # Final Save to MongoDB (Done once at the end - much faster)
        video_ids.reverse()
        await db.save_video_list_db(chat_id, video_ids)
        
        # Reset the forwarder checkpoint for THIS specific channel
        await db.save_forwarder_checkpoint(chat_id, 0)
        
        await status_msg.edit(
            f"✅ **Indexing Complete!**\n\n"
            f"Total Videos in DB: `{len(video_ids)}`\n"
            f"New Videos Added: `{new_videos_count}`\n\n"
            f"💡 **Checkpoint Reset** for this channel."
        )

    except Exception as e:
        logger.error(f"Indexing error: {e}")
        try:
            await status_msg.edit(f"❌ **Error:** `{e}`")
        except:
            pass
    finally:
        # Ensure user is removed from set so they can index again later
        ACTIVE_INDEXING.discard(user_id)
