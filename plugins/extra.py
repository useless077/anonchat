# plugins/extra.py

import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from database.users import db
from utils import get_online_users_count

# --- BROADCAST COMMAND ---
@Client.on_message(filters.private & filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_cmd(client: Client, message: Message):
    """Sends a message to all users of the bot."""
    if len(message.command) < 2:
        await message.reply("Usage: `/broadcast Your message here`")
        return

    broadcast_text = message.text.split(None, 1)[1]
    
    # Get all user IDs from the database
    users_cursor = db.users.find({}, {"_id": 1})
    user_ids = [user["_id"] async for user in users_cursor]
    
    total_users = len(user_ids)
    if total_users == 0:
        await message.reply("No users found in the database to broadcast.")
        return

    success_count = 0
    failed_count = 0
    blocked_users = []

    # Initial status message
    status_msg = await message.reply(f"📢 Broadcasting to {total_users} users... Please wait.")

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
        f"✅ **Broadcast Complete!**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Successful: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"🚫 Blocked/Deleted: {len(blocked_users)}"
    )

    if blocked_users:
        print(f"[BROADCAST] Users who blocked the bot: {blocked_users}")


# --- STATUS COMMAND ---
@Client.on_message(filters.private & filters.command("status") & filters.user(OWNER_ID))
async def status_cmd(client: Client, message: Message):
    """Shows the overall bot statistics."""
    
    # Get stats from database
    total_users = await db.users.count_documents({})
    active_chats = await db.users.count_documents({"status": "chatting"}) // 2 # Each chat has 2 users
    online_users = get_online_users_count(minutes=5) # Users active in last 5 mins

    # Format the status message
    status_text = (
        f"🤖 **Bot Statistics**\n\n"
        f"👥 **Total Users:** `{total_users}`\n"
        f"💬 **Active Chats:** `{active_chats}`\n"
        f"🟢 **Online Users (5 min):** `{online_users}`\n\n"
        f"⏰ Checked at: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )

    await message.reply(status_text, parse_mode=enums.ParseMode.MARKDOWN)
