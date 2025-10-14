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
# (This part is likely fine, but let's keep it consistent)
@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_cmd(client: Client, message: Message):
    """Sends a message to all users of the bot."""
    print(f"[Broadcast] Command received from {message.from_user.id}")
    # ... rest of the broadcast code ...
    if len(message.command) < 2:
        await message.reply("**ᴜꜱᴀɢᴇ:** `/broadcast Your message here`", parse_mode=enums.ParseMode.HTML)
        return

    broadcast_text = message.text.split(None, 1)[1]
    user_ids = await db.get_all_users()
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
    print(f"[Status] Command received from {message.from_user.id}")
    # ... rest of the status code ...
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


# --- Command: /autodelete on|off (HEAVILY LOGGED) ---
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_autodelete(client: Client, message: Message):
    # THIS IS THE MOST IMPORTANT LOG. IF THIS DOESN'T APPEAR, THE HANDLER IS NOT TRIGGERED.
    print(f"[AutoDelete Command] 🔥 HANDLER TRIGGERED! Message: '{message.text}' in chat {message.chat.id} by user {message.from_user.id}")

    try:
        print("[AutoDelete Command] Checking if user is admin...")
        user = await client.get_chat_member(message.chat.id, message.from_user.id)
        
        # Use Pyrogram enums for more reliable admin status checking
        if user.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            print(f"[AutoDelete Command] User {message.from_user.id} is NOT an admin. Status: {user.status}")
            return await message.reply("❌ Only admins can use this command.")
        print(f"[AutoDelete Command] User {message.from_user.id} is an admin. Status: {user.status}. OK.")

        print("[AutoDelete Command] Checking bot's own permissions...")
        bot_member = await client.get_chat_member(message.chat.id, client.me.id)
        if not bot_member.privileges or not bot_member.privileges.can_delete_messages:
            print(f"[AutoDelete Command] Bot does NOT have delete permission.")
            return await message.reply(
                "⚠️ **ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.**\n\n"
                "🛠️ **ᴘʟᴇᴀꜱᴇ ɢɪᴠᴇ ᴍᴇ ᴛʜᴇ 'ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ' ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.**"
            )
        print("[AutoDelete Command] Bot has delete permission. OK.")

        cmd_arg = message.command[1].lower() if len(message.command) > 1 else None
        print(f"[AutoDelete Command] Parsed argument: '{cmd_arg}'")

        if not cmd_arg:
            print("[AutoDelete Command] No argument provided, checking status...")
            status = await db.get_autodelete_status(message.chat.id)
            status_text = "ON ✅" if status else "OFF ❌"
            print(f"[AutoDelete Command] Status from DB: {status_text}")
            return await message.reply(f"AutoDelete is currently **{status_text}**")

        if cmd_arg == "on":
            print("[AutoDelete Command] Argument is 'on', setting status in DB...")
            await db.set_autodelete(message.chat.id, True)
            print(f"[AutoDelete Command] Successfully ENABLED for chat {message.chat.id}")
            return await message.reply(
                "🧹 AutoDelete **enabled!**\n\n"
                "All media (except text & voice) will be deleted after **1 hour.**"
            )

        elif cmd_arg == "off":
            print("[AutoDelete Command] Argument is 'off', setting status in DB...")
            await db.set_autodelete(message.chat.id, False)
            print(f"[AutoDelete Command] Successfully DISABLED for chat {message.chat.id}")
            return await message.reply("🧹 AutoDelete **disabled.**")

        else:
            print(f"[AutoDelete Command] Invalid argument: '{cmd_arg}'")
            return await message.reply("Usage: `/autodelete on` or `/autodelete off`", quote=True)

    except Exception as e:
        print(f"[AutoDelete Command] ❌ ERROR: {e}")
        import traceback
        traceback.print_exc() # This will print the full error details
        await message.reply("⚠️ Something went wrong while processing this command.")


# --- AUTO DELETE MEDIA HANDLER (HEAVILY LOGGED) ---
@Client.on_message(filters.group & filters.media, group=99) # Simplified filter
async def auto_delete_media(client: Client, message: Message):
    # THIS IS THE CANARY LOG FOR THE MEDIA HANDLER
    print(f"[AutoDelete Media] 🔥🔥 MEDIA HANDLER TRIGGERED! Message ID: {message.id} in chat {message.chat.id}")

    # We don't need to check for media anymore because the filter does it.
    # We also don't need to exclude the command, because commands are not media.

    chat_id = message.chat.id
    
    print(f"[AutoDelete Media] Checking autodelete status for chat {chat_id}...")
    try:
        status = await db.get_autodelete_status(chat_id)
        if not status:
            print(f"[AutoDelete Media] Autodelete is OFF for chat {chat_id}. Ignoring message.")
            return  # autodelete is off for this group
    except Exception as e:
        print(f"[AutoDelete Media] ❌ ERROR checking status for chat {chat_id}: {e}")
        return

    print(f"[AutoDelete Media] Autodelete is ON for chat {chat_id}. Scheduling deletion for message {message.id}.")
    
    # Create a background task for deletion. This is non-blocking.
    asyncio.create_task(_delete_message_after_delay(client, chat_id, message.id))

# --- AUTO DELETE BOT'S OWN MEDIA HANDLER ---
@Client.on_message(filters.group & filters.media & filters.outgoing, group=98)
async def auto_delete_bot_media(client: Client, message: Message):
    # THIS IS THE CANARY LOG FOR THE BOT'S MEDIA HANDLER
    print(f"[AutoDelete Bot Media] 🔥🔥 BOT MEDIA HANDLER TRIGGERED! Message ID: {message.id} in chat {message.chat.id}")

    chat_id = message.chat.id
    
    print(f"[AutoDelete Bot Media] Checking autodelete status for chat {chat_id}...")
    try:
        status = await db.get_autodelete_status(chat_id)
        if not status:
            print(f"[AutoDelete Bot Media] Autodelete is OFF for chat {chat_id}. Ignoring message.")
            return  # autodelete is off for this group
    except Exception as e:
        print(f"[AutoDelete Bot Media] ❌ ERROR checking status for chat {chat_id}: {e}")
        return

    print(f"[AutoDelete Bot Media] Autodelete is ON for chat {chat_id}. Scheduling deletion for message {message.id}.")
    
    # Create a background task for deletion. This is non-blocking.
    asyncio.create_task(_delete_message_after_delay(client, chat_id, message.id))

# --- HELPER FUNCTION FOR DELETION ---
async def _delete_message_after_delay(client: Client, chat_id: int, message_id: int):
    """A separate task to sleep and then delete the message."""
    print(f"[AutoDelete Task] Task started for message {message_id} in chat {chat_id}. Waiting for {delete_delay} seconds.")
    await asyncio.sleep(delete_delay)
    try:
        await client.delete_messages(chat_id, message_id)
        print(f"[AutoDelete Task] 🧹 Successfully deleted message {message_id} from chat {chat_id}")
    except Exception as e:
        print(f"[AutoDelete Task] ❌ Could not delete message {message_id} in chat {chat_id}: {e}")
