# plugins/extra.py
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db
from utils import get_online_users_count

delete_delay = 3600  # 1 hour (in seconds)

# --- BROADCAST COMMAND ---
@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_cmd(client: Client, message: Message):
    """Sends a message to all users of the bot."""
    if len(message.command) < 2:
        await message.reply("**ᴜꜱᴀɢᴇ:** `/broadcast Your message here`", parse_mode=enums.ParseMode.HTML)
        return

    broadcast_text = message.text.split(None, 1)[1]
    
    # --- CHANGE 1: Using new database method ---
    user_ids = await db.get_all_users() # Assuming you add this method to db.py
    
    total_users = len(user_ids)
    if total_users == 0:
        await message.reply("**ɴᴏ ᴜꜱᴇʀꜱ ꜰᴏᴜɴᴅ ɪɴ ᴛʜᴇ ᴅᴀᴛᴀʙᴀꜱᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.**", parse_mode=enums.ParseMode.HTML)
        return

    success_count = 0
    failed_count = 0
    blocked_users = []

    status_msg = await message.reply(f"📢 **ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ ᴛᴏ {total_users} ᴜꜱᴇʀꜱ... ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ.**", parse_mode=enums.ParseMode.HTML)

    for user_id in user_ids:
        try:
            await client.send_message(user_id, broadcast_text)
            success_count += 1
            await asyncio.sleep(0.1) 
        except Exception as e:
            failed_count += 1
            print(f"[BROADCAST] Failed to send to {user_id}: {e}")
            if "FORBIDDEN" in str(e) or "PEER_ID_INVALID" in str(e):
                blocked_users.append(user_id)
    
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
    
    # --- CHANGE 2: Using new database methods for stats ---
    total_users = await db.get_total_users()
    active_chats = await db.get_active_chats()
    online_users = get_online_users_count(minutes=5)
    total_groups = await db.get_total_groups()

    status_text = (
        f"🤖 **ʙᴏᴛ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ**\n\n"
        f"👥 **ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:** `{total_users}`\n"
        f"💬 **ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛꜱ:** `{active_chats}`\n"
        f"🟢 **ᴏɴʟɪɴᴇ ᴜꜱᴇʀꜱ (5 ᴍɪɴ):** `{online_users}`\n"
        f"🌐 **ᴛᴏᴛᴀʟ ɢʀᴏᴜᴘꜱ:** `{total_groups}`\n\n"
        f"⏰ **ᴄʜᴇᴄᴋᴇᴅ ᴀᴛ:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )

    await message.reply(status_text, parse_mode=enums.ParseMode.MARKDOWN)

# --- Command: /autodelete on|off (UPDATED) ---
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_autodelete(client: Client, message: Message):
    try:
        print(f"[AutoDelete] Command received in chat {message.chat.id} by user {message.from_user.id}")
        
        # Check if user is admin
        user = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (user.status in ("administrator", "creator")):
            print(f"[AutoDelete] User {message.from_user.id} is not an admin")
            return await message.reply("❌ Only admins can use this command.")

        # Check bot delete permission
        bot_member = await client.get_chat_member(message.chat.id, client.me.id)
        if not bot_member.privileges or not bot_member.privileges.can_delete_messages:
            print(f"[AutoDelete] Bot doesn't have delete permission in chat {message.chat.id}")
            return await message.reply(
                "⚠️ **ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.**\n\n"
                "🛠️ **ᴘʟᴇᴀꜱᴇ ɢɪᴠᴇ ᴍᴇ ᴛʜᴇ 'ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ' ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.**"
            )

        # Parse command argument safely
        text_parts = message.text.split()
        cmd_arg = text_parts[1].lower() if len(text_parts) > 1 else None

        if not cmd_arg:
            # --- CHANGE: Check status from database ---
            try:
                status = await db.get_autodelete_status(message.chat.id)
                status_text = "ON ✅" if status else "OFF ❌"
                print(f"[AutoDelete] Current status for chat {message.chat.id}: {status}")
                return await message.reply(f"AutoDelete is currently **{status_text}**")
            except Exception as e:
                print(f"[AutoDelete] Error getting status: {e}")
                return await message.reply(f"❌ Error checking autodelete status: {e}")

        if cmd_arg == "on":
            # --- CHANGE: Save status to database ---
            try:
                await db.set_autodelete(message.chat.id, True)
                print(f"[AutoDelete] Enabled for chat {message.chat.id}")
                return await message.reply(
                    "🧹 AutoDelete **enabled!**\n\n"
                    "All media (except text & voice) will be deleted after **1 hour.**"
                )
            except Exception as e:
                print(f"[AutoDelete] Error enabling: {e}")
                return await message.reply(f"❌ Error enabling autodelete: {e}")

        elif cmd_arg == "off":
            # --- CHANGE: Save status to database ---
            try:
                await db.set_autodelete(message.chat.id, False)
                print(f"[AutoDelete] Disabled for chat {message.chat.id}")
                return await message.reply("🧹 AutoDelete **disabled.**")
            except Exception as e:
                print(f"[AutoDelete] Error disabling: {e}")
                return await message.reply(f"❌ Error disabling autodelete: {e}")

        else:
            return await message.reply("Usage: `/autodelete on` or `/autodelete off`", quote=True)

    except Exception as e:
        print(f"[AutoDelete] Error in toggle_autodelete: {e}")
        await message.reply("⚠️ Something went wrong while processing this command.")


# --- AUTO DELETE MEDIA HANDLER (UPDATED) ---
@Client.on_message(filters.group & ~filters.command(["autodelete"]), group=99)
async def auto_delete_media(client: Client, message: Message):
    chat_id = message.chat.id
    
    # --- CHANGE: Check status from database ---
    try:
        status = await db.get_autodelete_status(chat_id)
        if not status:
            return  # autodelete off for this group
    except Exception as e:
        print(f"[AutoDelete] Error checking status in auto_delete_media: {e}")
        return  # If we can't check status, assume autodelete is off

    # Exclude text & voice messages
    if message.text or message.voice:
        return

    # Also exclude service messages (like user joined, left, etc.)
    if message.service:
        return

    try:
        print(f"[AutoDelete] Scheduling deletion for message {message.id} in chat {chat_id}")
        # Schedule deletion after delay
        await asyncio.sleep(delete_delay)
        await client.delete_messages(chat_id, message.id)
        print(f"[AutoDelete] 🧹 Deleted message {message.id} from chat {chat_id}")

    except Exception as e:
        # This can happen if the message was already deleted or bot was kicked
        print(f"[AutoDelete] Error deleting message {message.id} in chat {chat_id}: {e}")
