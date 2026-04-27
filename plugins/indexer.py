import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db
from utils import autodelete_enabled_chats

logger = logging.getLogger(__name__)

# Global State
INDEX_LOCK = asyncio.Lock()
INDEX_CANCEL = False

# Regex to detect Telegram Links
LINK_REGEX = re.compile(r"(https?://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")


@Client.on_message(filters.private & filters.command("index"))
async def ask_link(client: Client, message: Message):
    """Handles forwarded messages or links to trigger indexing."""
    
    # 1. Parse Chat ID and Message ID
    chat_id = None
    last_msg_id = None

    if message.text:
        match = LINK_REGEX.match(message.text)
        if not match:
            return # Not a valid link, ignore

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

    # 3. Start Indexing (Non-Blocking)
    # NOTE: We run this in a background task so the /index command replies immediately.
    asyncio.create_task(run_indexing(client, message, chat_id, last_msg_id))


async def run_indexing(client: Client, message: Message, chat_id, start_id):
    """Main loop to fetch and save video IDs to MongoDB."""
    global INDEX_CANCEL
    INDEX_CANCEL = False
    
    async with INDEX_LOCK:
        # Load existing IDs from MongoDB to prevent duplicates
        video_ids = await db.get_video_list_db(chat_id)
        existing_ids_set = set(video_ids)
        
        count = 0
        skipped = 0
        
        # Load existing to track new additions specifically
        new_videos_count = 0

        try:
            # Iterate backwards from the starting message
            async for msg in client.get_chat_history(chat_id, offset_id=start_id):
                
                if INDEX_CANCEL:
                    await message.reply("🛑 **Indexing Cancelled.**")
                    return

                if msg.photo or msg.video:
                    if msg.id not in existing_ids_set:
                        existing_ids_set.add(msg.id)
                        video_ids.append(msg.id)
                        new_videos_count += 1
                    else:
                        skipped += 1

                # Update UI every 20 messages (Safe)
                if new_videos_count % 20 == 0 and new_videos_count > 0:
                    try:
                        await message.edit_text(
                            f"📥 **Indexing...**\n"
                            f"New: `{new_videos_count}` | Skipped: `{skipped}`\n"
                            f"⏳ Processing ID: `{msg.id}`..."
                        )
                    except Exception:
                        pass # If we can't edit, we keep processing

            # Final Save to MongoDB (Optimized: Sort and Save once)
            if video_ids:
                video_ids.reverse() # Oldest first for forwarder
                await db.save_video_list_db(chat_id, video_ids)
                
                # Reset the forwarder checkpoint for THIS specific channel
                await db.save_forwarder_checkpoint(chat_id, 0)
                
                try:
                    await message.edit_text(
                        f"✅ **Indexing Complete!**\n\n"
                        f"Total Videos in DB: `{len(video_ids)}`\n"
                        f"New Videos Added: `{new_videos_count}`\n\n"
                        f"💡 **Checkpoint Reset** for this channel."
                    )
                except Exception:
                    pass
                return

        except Exception as e:
            logger.error(f"Indexing Error: {e}")
            try:
                await message.reply(f"❌ **Error:** `{e}`")
            except:
                pass
