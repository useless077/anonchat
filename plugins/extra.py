# plugins/extra.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db
from utils import get_online_users_count

# --- BROADCAST COMMAND ---
@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_cmd(client: Client, message: Message):
    """Sends a message to all users of the bot."""
    if len(message.command) < 2:
        await message.reply("**ᴜꜱᴀɢᴇ:** `/broadcast Your message here`", parse_mode=enums.ParseMode.HTML)
        return

    broadcast_text = message.text.split(None, 1)[1]
    
    # --- IMPORTANT FIX: Get only PRIVATE user IDs ---
    # Group IDs are negative, so we only fetch positive IDs to avoid broadcasting to groups.
    users_cursor = db.users.find({"_id": {"$gt": 0}}, {"_id": 1})
    user_ids = [user["_id"] async for user in users_cursor]
    
    total_users = len(user_ids)
    if total_users == 0:
        await message.reply("**ɴᴏ ᴜꜱᴇʀꜱ ꜰᴏᴜɴᴅ ɪɴ ᴛʜᴇ ᴅᴀᴛᴀʙᴀꜱᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.**", parse_mode=enums.ParseMode.HTML)
        return

    success_count = 0
    failed_count = 0
    blocked_users = []

    # Initial status message
    status_msg = await message.reply(f"📢 **ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ ᴛᴏ {total_users} ᴜꜱᴇʀꜱ... ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ.**", parse_mode=enums.ParseMode.HTML)

    for user_id in user_ids:
        try:
            await client.send_message(user_id, broadcast_text)
            success_count += 1
            # Add a small delay to avoid FloodWait
            await asyncio.sleep(0.1) 
        except Exception as e:
            failed_count += 1
            print(f"[BROADCAST] Failed to send to {user_id}: {e}")
            # Check if the user blocked the bot
            if "FORBIDDEN" in str(e) or "PEER_ID_INVALID" in str(e):
                blocked_users.append(user_id)
    
    # Update the status message
    await status_msg.edit_text(
        f"✅ **ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇ!**\n\n"
        f"👥 **ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:** {total_users}\n"
        f"✅ **ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ:** {success_count}\n"
        f"❌ **ꜰᴀɪʟᴇᴅ:** {failed_count}\n"
        f"🚫 **ʙʟᴏᴄᴋᴇᴅ/ᴅᴇʟᴇᴛᴇᴅ:** {len(blocked_users)}",
        parse_mode=enums.ParseMode.HTML
    )

    if blocked_users:
        print(f"[BROADCAST] Users who blocked the bot: {blocked_users}")


# --- STATUS COMMAND ---
@Client.on_message(filters.private & filters.command("status") & filters.user(ADMIN_IDS))
async def status_cmd(client: Client, message: Message):
    """Shows the overall bot statistics."""
    
    # Get stats from database
    total_users = await db.users.count_documents({"_id": {"$gt": 0}}) # Count only private users
    active_chats = await db.users.count_documents({"status": "chatting"}) // 2 # Each chat has 2 users
    online_users = get_online_users_count(minutes=5) # Users active in last 5 mins
    
    # --- NEW: Get Total Groups ---
    total_groups = await db.users.count_documents({"_id": {"$lt": 0}})

    # Format the status message
    status_text = (
        f"🤖 **ʙᴏᴛ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ**\n\n"
        f"👥 **ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:** `{total_users}`\n"
        f"💬 **ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛꜱ:** `{active_chats}`\n"
        f"🟢 **ᴏɴʟɪɴᴇ ᴜꜱᴇʀꜱ (5 ᴍɪɴ):** `{online_users}`\n"
        f"🌐 **ᴛᴏᴛᴀʟ ɢʀᴏᴜᴘꜱ:** `{total_groups}`\n\n"
        f"⏰ **ᴄʜᴇᴄᴋᴇᴅ ᴀᴛ:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )

    await message.reply(status_text, parse_mode=enums.ParseMode.MARKDOWN)
