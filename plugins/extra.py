# plugins/extra.py
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS
from database.users import db
from utils import get_online_users_count

# to store which chats have autodelete ON
auto_delete_enabled = {}
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

# --- Command: /autodelete on|off ---
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_autodelete(client: Client, message: Message):
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    if not (user.status in ("administrator", "creator")):
        return await message.reply("❌ Only admins can use this command.")

    # Check bot permissions first
    bot_member = await client.get_chat_member(message.chat.id, client.me.id)
    if not bot_member.privileges or not bot_member.privileges.can_delete_messages:
        return await message.reply(
            "⚠️ **ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.**\n\n"
            "🛠️ **ᴘʟᴇᴀꜱᴇ ɢɪᴠᴇ ᴍᴇ ᴛʜᴇ ‘ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ’ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.**"
        )

    args = message.text.split(None, 1)
    if len(args) == 1:
        status = "ON ✅" if auto_delete_enabled.get(message.chat.id) else "OFF ❌"
        return await message.reply(f"AutoDelete is currently **{status}**")

    cmd = args[1].lower()
    if cmd == "on":
        auto_delete_enabled[message.chat.id] = True
        await message.reply("🧹 AutoDelete **enabled!** All media (except text & voice) will be deleted after **1 hour.**")
    elif cmd == "off":
        auto_delete_enabled.pop(message.chat.id, None)
        await message.reply("🧹 AutoDelete **disabled.**")
    else:
        await message.reply("Usage: `/autodelete on` or `/autodelete off`", quote=True)



# --- AUTO DELETE MEDIA HANDLER ---
@Client.on_message(filters.group, group=99)
async def auto_delete_media(client: Client, message: Message):
    chat_id = message.chat.id
    if not auto_delete_enabled.get(chat_id):
        return  # autodelete off for this group

    # Exclude text & voice
    if message.text or message.voice:
        return

    try:
        # Check bot's permissions
        bot_member = await client.get_chat_member(chat_id, (await client.get_me()).id)
        if not bot_member.can_delete_messages:
            print(f"[AutoDelete] ❌ Bot has no delete permission in chat {chat_id}")
            return

        # Delay before deletion
        await asyncio.sleep(delete_delay)
        await client.delete_messages(chat_id, message.id)
        print(f"[AutoDelete] 🧹 Deleted message {message.id} from chat {chat_id}")

    except Exception as e:
        print(f"[AutoDelete] Error deleting message: {e}")
