import re
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db

logger = logging.getLogger(__name__)

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

    # 3. Start Indexing (NON-BLOCKING)
    # We use create_task so it runs in background
    # We DO NOT await it, otherwise /start will freeze until indexing finishes
    status_msg = await message.reply(f"🔄 **Starting Index...**\nSource: `{chat_id}`\nFrom ID: `{last_msg_id}`")
    
    asyncio.create_task(run_indexing(client, status_msg, chat_id, last_msg_id))


@Client.on_message(filters.command("cancel_index") & filters.user(ADMIN_IDS))
async def cancel_index_cmd(client: Client, message: Message):
    """Cancels the current indexing process."""
    global INDEX_CANCEL
    INDEX_CANCEL = True
    await message.reply("🛑 **Indexing Cancelled.**")


async def run_indexing(pyro_client: Client, status_msg: Message, chat_id, start_id):
    """Main loop to fetch and save video IDs to MongoDB."""
    global INDEX_CANCEL
    INDEX_CANCEL = False
    
    async with INDEX_LOCK:
        # Load existing IDs from MongoDB to prevent duplicates
        video_ids = await db.get_video_list_db(chat_id)
        existing_ids_set = set(video_ids)
        
        count = 0
        skipped = 0
        
        # Use get_chat_history
        try:
            # Iterate backwards from the starting message.
            # FIX: Added limit=10000 to prevent runaway loops
            # FIX: Added asyncio.sleep(0.05) to prevent bot from feeling "blocked/laggy"
            async for msg in pyro_client.get_chat_history(chat_id, offset_id=start_id, limit=10000):
                
                if INDEX_CANCEL:
                    await status_msg.edit(f"🛑 **Cancelled.**\nNew Indexed: `{count}`")
                    return

                if msg.photo or msg.video:
                    if msg.id not in existing_ids_set:
                        existing_ids_set.add(msg.id)
                        video_ids.append(msg.id)
                        count += 1
                    else:
                        skipped += 1

                # CRITICAL FIX FOR "BLOCKING COMMANDS":
                # Even though this runs in a background task (create_task),
                # if it hogs the CPU/Database, other commands (/start, /search) feel slow.
                # We yield control back to the event loop every 50 messages.
                if count % 50 == 0:
                    await asyncio.sleep(0.05)

        except Exception as e:
            await status_msg.edit(f"❌ **Error:** {e}")
            return

        # Final Save to MongoDB
        try:
            # Sort: Oldest first for the forwarder
            video_ids.reverse()
            await db.save_video_list_db(chat_id, video_ids)
            
            # Reset the forwarder checkpoint for THIS specific channel
            await db.save_forwarder_checkpoint(chat_id, 0)
            
            await status_msg.edit(
                f"✅ **Indexing Complete!**\n\n"
                f"Total Videos in DB: `{len(video_ids)}`\n"
                f"New Videos Added: `{count}`\n\n"
                f"💡 **Checkpoint Reset** for this channel."
            )
        except Exception as e:
            logger.error(f"Final DB Save Error: {e}")
            await status_msg.edit(f"⚠️ Indexing finished but failed to save to DB: `{e}`")
