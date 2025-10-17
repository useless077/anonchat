# plugins/extra.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS, LOG_CHANNEL
from database.users import db
from utils import get_online_users_count, schedule_deletion, autodelete_enabled_chats

delete_delay = 3600  # 1 hour

# --- BROADCAST COMMAND ---
@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_cmd(client: Client, message: Message):
    print(f"[Broadcast] Command received from {message.from_user.id}")

    if len(message.command) < 2:
        return await message.reply("**Usage:** `/broadcast Your message here`", parse_mode=enums.ParseMode.MARKDOWN)

    broadcast_text = message.text.split(None, 1)[1]
    user_ids = await db.get_all_users()
    total_users = len(user_ids)
    if total_users == 0:
        return await message.reply("**No users found in the database.**")

    success_count = 0
    failed_count = 0
    blocked_users = []
    status_msg = await message.reply(f"📢 Broadcasting to {total_users} users...")

    for user_id in user_ids:
        try:
            await client.send_message(user_id, broadcast_text)
            success_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            failed_count += 1
            error_text = str(e).upper()
            print(f"[BROADCAST] Failed to send to {user_id}: {error_text}")
            if any(bad in error_text for bad in ["FORBIDDEN", "PEER_ID_INVALID", "USER_IS_DEACTIVATED"]):
                blocked_users.append(user_id)
                await db.remove_user(user_id)
                print(f"[BROADCAST] ❌ Removed blocked/deleted user {user_id} from DB.")

    await status_msg.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"👥 Total: `{total_users}`\n"
        f"✅ Success: `{success_count}`\n"
        f"❌ Failed: `{failed_count}`\n"
        f"🚫 Removed: `{len(blocked_users)}`",
        parse_mode=enums.ParseMode.MARKDOWN
    )

    if blocked_users:
        print(f"[BROADCAST] Removed users: {blocked_users}")

# --- STATUS COMMAND ---
@Client.on_message(filters.private & filters.command("status") & filters.user(ADMIN_IDS))
async def status_cmd(client: Client, message: Message):
    print(f"[Status] Command received from {message.from_user.id}")
    total_users = await db.get_total_users()
    active_chats = await db.get_active_chats()
    total_groups = await db.get_total_groups()
    online_users = get_online_users_count(minutes=5)

    status_text = (
        f"🤖 **Bot Statistics**\n\n"
        f"👥 **Total Users:** `{total_users}`\n"
        f"💬 **Active Chats (pairs):** `{active_chats}`\n"
        f"🟢 **Online (5 min):** `{online_users}`\n"
        f"🌐 **Total Groups Tracked:** `{total_groups}`\n\n"
        f"⏰ **Checked at:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC`"
    )

    await message.reply(status_text, parse_mode=enums.ParseMode.MARKDOWN)

# --- PRIVATE AUTO DELETE ---
@Client.on_message(~filters.text & filters.private)
async def auto_delete_private(client: Client, message: Message):
    """
    Auto-delete any non-text messages in private after 1 hour.
    """
    await schedule_deletion(client, message.chat.id, [message.id], delay=delete_delay)

# --- AUTODELETE COMMAND (group only) ---
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_autodelete(client: Client, message: Message):
    print(f"[AutoDelete Command] Triggered in {message.chat.id} by {message.from_user.id}")
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            return await message.reply("❌ Only group admins can use this command.")

        bot_member = await client.get_chat_member(message.chat.id, client.me.id)
        if not bot_member.privileges or not getattr(bot_member.privileges, "can_delete_messages", False):
            return await message.reply("⚠️ I need 'Delete Messages' permission to manage autodelete.")

        arg = message.command[1].lower() if len(message.command) > 1 else None
        if not arg:
            status = await db.get_autodelete_status(message.chat.id)
            return await message.reply(f"AutoDelete is currently **{'ON ✅' if status else 'OFF ❌'}**")

        if arg == "on":
            await db.set_autodelete_status(message.chat.id, True)
            autodelete_enabled_chats.add(message.chat.id)
            return await message.reply("🧹 AutoDelete **enabled** — media will be deleted after 1 hour.")
        elif arg == "off":
            await db.set_autodelete_status(message.chat.id, False)
            autodelete_enabled_chats.discard(message.chat.id)
            return await message.reply("🧹 AutoDelete **disabled**.")
        else:
            return await message.reply("Usage: `/autodelete on` or `/autodelete off`")
    except Exception as e:
        print(f"[AutoDelete Command] Error: {e}")
        return await message.reply("⚠️ Something went wrong while processing this command.")

# --- GROUP AUTO DELETE MEDIA ---
@Client.on_message(filters.group & filters.media, group=99)
async def auto_delete_group_media(client: Client, message: Message):
    """
    Delete media messages in groups if autodelete is enabled.
    """
    if message.chat.id not in autodelete_enabled_chats:
        return
    await schedule_deletion(client, message.chat.id, [message.id], delay=delete_delay)
