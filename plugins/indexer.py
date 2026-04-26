import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db

logger = logging.getLogger(__name__)

# ============================================
# CONFIG: Change this to your Source Channel ID
# ============================================
# You can hardcode it here, or add it to config.py
SOURCE_CHANNEL_ID = -1003222215181 # <--- PUT YOUR CHANNEL ID HERE

# ============================================
# INDEX COMMAND (SIMPLE & FAST)
# ============================================

@Client.on_message(filters.command("index") & filters.user(ADMIN_IDS))
async def run_full_index(client: Client, message: Message):
    """
    Fetches ALL videos/photos from the source channel and saves them to the database.
    Overwrites existing data for this channel.
    """
    
    # 1. Send initial status
    status_msg = await message.reply(f"🔄 **Starting Full Index...**\nSource: `{SOURCE_CHANNEL_ID}`")

    # 2. Load existing IDs to prevent duplicates (Optional, but good for speed)
    existing_ids = set()
    try:
        existing_data = await db.get_video_list_db(SOURCE_CHANNEL_ID)
        if existing_data:
            existing_ids = set(existing_data)
            logger.info(f"Loaded {len(existing_ids)} existing IDs from DB to skip duplicates.")
    except Exception as e:
        logger.warning(f"Could not load existing IDs: {e}")

    new_videos = []

    # 3. Fetch History
    try:
        # We iterate through history. 
        # limit=0 (no limit) means fetch as much as possible.
        async for msg in client.get_chat_history(SOURCE_CHANNEL_ID, limit=200):
            
            # Only index Videos and Photos
            if msg.video or msg.photo:
                if msg.id not in existing_ids:
                    new_videos.append(msg.id)
                    existing_ids.add(msg.id) # Add to set to skip memory duplicates within this run

                # Update UI every 20 videos
                if len(new_videos) % 20 == 0:
                    await status_msg.edit(f"📥 **Indexing...**\nNew Found: `{len(new_videos)}`")

    except Exception as e:
        await status_msg.edit(f"❌ **Error:** `{e}`\n\nCould not fetch history. Make sure bot is Admin in the channel.")
        return

    # 4. Save to Database
    if not new_videos:
        return await status_msg.edit("✅ **No new videos found.**")

    # Sort: Oldest first for Forwarder
    new_videos.reverse()

    try:
        await db.save_video_list_db(SOURCE_CHANNEL_ID, new_videos)
        
        # Reset checkpoint for this channel so forwarder starts from beginning
        await db.save_forwarder_checkpoint(SOURCE_CHANNEL_ID, 0)
        
        await status_msg.edit(
            f"✅ **Indexing Complete!**\n\n"
            f"📂 Total Videos in DB: `{len(new_videos)}`\n"
            f"🆕 New Videos Added: `{len(new_videos)}`\n\n"
            f"💡 **Checkpoint Reset.**"
        )
    except Exception as e:
        await status_msg.edit(f"⚠️ Indexed but failed to save: `{e}`")
