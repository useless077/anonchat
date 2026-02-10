import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import FORWARDER_SOURCE_ID, FORWARDER_DEST_IDS, FORWARD_DELAY, AUTO_DELETE_DELAY, LOG_CHANNEL
from database.users import db 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Queues and State ---
post_queue = asyncio.Queue()
processed_media_groups = set()

async def delete_after_delay(client, chat_id, message_ids, delay):
    """Waits for X seconds then deletes the message."""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_ids)
        logger.info(f"🗑️ Deleted message(s) {message_ids} in {chat_id}")
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")

async def forward_worker(client):
    """
    Background worker that takes media from the queue and posts them 
    with a 15-minute delay.
    """
    logger.info("🚀 Auto Forwarder Worker Started")
    
    # Get Bot Username
    me = await client.get_me()
    bot_username = me.username if me.username else "TamilAnonymousChatBot"
    start_link = f"https://t.me/{bot_username}?start=start"

    while True:
        # 1. Get the next message from the queue
        message = await post_queue.get()
        
        # Skip if message object is invalid (rare edge case)
        if not message: 
            continue

        logger.info(f"📤 Processing message {message.id} from source...")
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share me for more videos", url=start_link)]
        ])

        # 2. Send to all Destination Groups
        for chat_id in FORWARDER_DEST_IDS:
            try:
                sent_msg = await message.copy(
                    chat_id=chat_id, 
                    caption=message.caption, 
                    reply_markup=reply_markup
                )
                
                logger.info(f"✅ Sent to {chat_id}. Scheduling delete in 5 mins...")
                asyncio.create_task(
                    delete_after_delay(client, chat_id, sent_msg.id, AUTO_DELETE_DELAY)
                )

                # ---------------------------------------------------------
                # --- NEW: LOG TO LOG CHANNEL ---
                # ---------------------------------------------------------
                try:
                    log_caption = (
                        f"📤 **Media Forwarded Successfully**\n"
                        f"🆔 **Source Msg ID:** `{message.id}`\n"
                        f"🎯 **Sent to Chat ID:** `{chat_id}`\n\n"
                        f"📝 **Original Caption:**\n{message.caption or 'No Caption'}"
                    )
                    # Copy the media to log channel with custom caption
                    await message.copy(
                        LOG_CHANNEL, 
                        caption=log_caption,
                        parse_mode="markdown"
                    )
                    logger.info(f"📝 Logged forwarded media to {LOG_CHANNEL}")
                except Exception as log_e:
                    logger.error(f"❌ Failed to log to channel: {log_e}")
                # ---------------------------------------------------------

            except Exception as e:
                logger.error(f"❌ Failed to send to {chat_id}: {e}")

        # 3. Update the Database Checkpoint so we don't post this again
        await db.save_forwarder_checkpoint(FORWARDER_SOURCE_ID, message.id)
        logger.info(f"💾 Checkpoint saved: Message {message.id}")

        # 4. Wait for 15 minutes
        logger.info(f"⏳ Waiting {FORWARD_DELAY // 60} minutes before next post...")
        await asyncio.sleep(FORWARD_DELAY)


async def catch_up_history(client):
    """
    Runs on startup. Checks for missed videos (history) and adds them to queue.
    """
    logger.info("🔍 Checking for missed videos...")
    
    # 1. Get the last message ID we processed
    last_processed_id = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)
    logger.info(f"Last processed ID: {last_processed_id}")
    
    if last_processed_id == 0:
        logger.info("⚠️ First run. Fetching ALL HISTORY (Oldest to Newest)...")
    else:
        logger.info("⚠️ Bot was offline. Fetching missed videos...")

    # 2. Iterate backwards from the latest message in the channel
    offset_id = 0
    buffer = []
    
    try:
        while True:
            # Fetch 100 messages at a time (Going backwards)
            messages = await client.get_chat_history(FORWARDER_SOURCE_ID, limit=100, offset_id=offset_id)
            
            if not messages:
                break
            
            # Check each message
            for msg in messages:
                # If we reached a message ID that is <= our checkpoint, stop.
                # This means we have processed everything NEWER than this ID.
                if msg.id <= last_processed_id:
                    # If we found our checkpoint, add whatever we collected (which are the missed ones)
                    # Reverse the buffer because we fetched backwards (New -> Old), 
                    # but we want to post Old -> New.
                    if buffer:
                        buffer.reverse()
                        logger.info(f"📦 Found {len(buffer)} missed videos. Adding to queue...")
                        for m in buffer:
                            await post_queue.put(m)
                    return # Stop fetching history

                # If it's media, add to buffer
                if msg.photo or msg.video:
                    buffer.append(msg)
            
            # Move the offset back further
            offset_id = messages[-1].id
            await asyncio.sleep(1) # Small sleep to be nice to Telegram API

        # If loop finishes without hitting checkpoint (last_processed_id was 0 or invalid)
        # This means we processed the entire channel history.
        if buffer:
            buffer.reverse()
            logger.info(f"📦 Finished history scan. Found {len(buffer)} total videos. Adding to queue...")
            for m in buffer:
                await post_queue.put(m)
                
    except Exception as e:
        logger.error(f"Error catching up history: {e}")


@Client.on_message(filters.chat(FORWARDER_SOURCE_ID) & (filters.photo | filters.video))
async def catch_media(client, message):
    """
    Listener for LIVE messages.
    Only adds to queue if it's a NEW message (newer than our checkpoint).
    """
    # We do a quick check here to avoid duplicates in extreme edge cases,
    # though the worker handles the saving.
    last_id = await db.get_forwarder_checkpoint(FORWARDER_SOURCE_ID)
    
    # If this message is older than or equal to our checkpoint, ignore it.
    # (This handles cases where the bot processes history but also receives updates)
    if message.id <= last_id:
        return

    media_group_id = message.media_group_id

    if not media_group_id:
        await post_queue.put(message)
        logger.info(f"➕ [LIVE] Added single media {message.id} to queue.")
        return

    if media_group_id in processed_media_groups:
        return

    try:
        processed_media_groups.add(media_group_id)
        logger.info(f"📦 [LIVE] Detected Album: {media_group_id}. Fetching...")
        media_messages = await client.get_media_group(message.chat.id, message.id)
        
        for msg in media_messages:
            await post_queue.put(msg)
            logger.info(f"➕ [LIVE] Added {msg.id} (from album) to queue.")
            
    except Exception as e:
        logger.error(f"Error processing live media group: {e}")
        if media_group_id in processed_media_groups:
            processed_media_groups.remove(media_group_id)
