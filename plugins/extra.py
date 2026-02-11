# plugins/extra.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS, LOG_CHANNEL
from database.users import db
from utils import get_online_users_count, schedule_deletion, autodelete_enabled_chats, AUTO_DELETE_DELAY

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

# --- AUTODELETE COMMAND (Group Only) ---
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_autodelete(client: Client, message: Message):
    print(f"[AutoDelete Command] Triggered in {message.chat.id} by {message.from_user.id}")
    
    # 1. Check if user is Admin
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            return await message.reply("❌ Only group admins can use this command.")
    except Exception:
        return await message.reply("❌ Error checking your permissions.")

    # 2. Check if Bot has Delete Permission
    try:
        bot_member = await client.get_chat_member(message.chat.id, client.me.id)
        if not bot_member.privileges or not getattr(bot_member.privileges, "can_delete_messages", False):
            # REQUESTED MESSAGE: "hey idiot first give me delete permission then use this function"
            return await message.reply("Hey idiot, first give me **Delete Messages** permission then use this function! 🤬")
    except Exception:
        return await message.reply("⚠️ I couldn't check my own permissions.")

    arg = message.command[1].lower() if len(message.command) > 1 else None
    
    if not arg:
        status = await db.get_autodelete_status(message.chat.id)
        return await message.reply(f"AutoDelete is currently **{'ON ✅' if status else 'OFF ❌'}**")

    if arg == "on":
        await db.set_autodelete_status(message.chat.id, True)
        autodelete_enabled_chats.add(message.chat.id)
        return await message.reply("🧹 AutoDelete **enabled** — All media (Stickers, GIFs, Videos, etc.) will be deleted after 1 hour.")
    elif arg == "off":
        await db.set_autodelete_status(message.chat.id, False)
        autodelete_enabled_chats.discard(message.chat.id)
        return await message.reply("🧹 AutoDelete **disabled**.")
    else:
        return await message.reply("Usage: `/autodelete on` or `/autodelete off`")


# --- GLOBAL AUTO DELETE HANDLER ---
# This catches ALL media (Bot's and User's) in groups where autodelete is ON
@Client.on_message(
    filters.group & (
        filters.photo | 
        filters.video | 
        filters.audio | 
        filters.document | 
        filters.sticker | 
        filters.animation | 
        filters.voice
    ), 
    group=2
)
async def auto_delete_group_media(client: Client, message: Message):
    """
    Delete media messages (including Bot's own media) after 1 hour 
    if autodelete is enabled for the group.
    """
    chat_id = message.chat.id

    # Check if this group has AutoDelete enabled
    if chat_id not in autodelete_enabled_chats:
        return

    print(f"[AUTODELETE] Scheduling deletion of message {message.id} (Type: {message.media}) in chat {chat_id}")
    
    # Schedule deletion in the background (Non-blocking)
    asyncio.create_task(schedule_deletion(client, chat_id, [message.id], delay=AUTO_DELETE_DELAY))


# ==========================================================
#  AGGRESSIVE ANTI-SPAM SYSTEM
# ==========================================================

# Regex to catch: Links, Channel Invites, and Bot Usernames (@SomethingBot)
SPAM_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+|@\w+bot)'

@Client.on_message(
    filters.group & 
    filters.text & 
    filters.regex(SPAM_PATTERN) & 
    ~filters.user(ADMIN_IDS) & 
    ~filters.command(["ai", "autodelete", "start", "search", "next", "end", "myprofile", "profile", "cancel", "broadcast", "status"])
)
async def anti_spam_delete(client: Client, message: Message):
    """
    Automatically deletes messages containing links or bot tags from non-admins.
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id

        # Double check if user is an Admin in this specific group
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            return # Allow admins to post links

        # --- SPAM CHECK 1: Links & Bot Usernames ---
        # If the regex above caught it, delete immediately.
        await message.delete()
        await _log_spam(client, user_id, message, "Link or Bot Username")
        return

    except Exception as e:
        print(f"[ANTI_SPAM] Error: {e}")


@Client.on_message(
    filters.group & 
    filters.text & 
    ~filters.user(ADMIN_IDS) & 
    ~filters.command(["ai", "autodelete", "start", "search", "next", "end", "myprofile", "profile", "cancel", "broadcast", "status"])
)
async def anti_spam_heavy(client: Client, message: Message):
    """
    Checks for Long Messages and Forwarded Spam.
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id

        # Check if user is an Admin
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            return 

        text = message.text or ""
        reason = None

        # --- SPAM CHECK 2: Long Messages (Copy-Paste Spam) ---
        if len(text) > 300: # If message is longer than 300 chars
            reason = "Too Long Message"

        # --- SPAM CHECK 3: Forwarded from Channel (Ads) ---
        # Note: We don't block forwarded from *users*, only *channels* (forward_from_chat)
        elif message.forward_from_chat:
            reason = "Forwarded from Channel"

        if reason:
            await message.delete()
            await _log_spam(client, user_id, message, reason)
            return

    except Exception as e:
        print(f"[ANTI_SPAM HEAVY] Error: {e}")


async def _log_spam(client: Client, user_id: int, message: Message, reason: str):
    """Helper to log deletion."""
    try:
        # Get a snippet of the message
        text_snippet = (message.text or message.caption or "")[:50]
        
        log_text = (
            f"🚫 **Auto-Deleted Spam**\n\n"
            f"👤 **User:** <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"💬 **Group:** `{message.chat.title}`\n"
            f"⚠️ **Reason:** {reason}\n"
            f"📝 **Snippet:** `{text_snippet}...`"
        )
        await client.send_message(config.LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass
