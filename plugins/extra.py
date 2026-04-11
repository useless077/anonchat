import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import ADMIN_IDS, LOG_CHANNEL
from database.users import db
from utils import (
    get_online_users_count,
    schedule_deletion,
    autodelete_enabled_chats,
    AUTO_DELETE_DELAY
)

# ==========================================================
# 🆕 GROUP TRACKER (IMPORTANT FOR /status GROUP COUNT)
# ==========================================================

@Client.on_message(filters.group, group=0)
async def track_groups(client: Client, message: Message):
    """Automatically store groups where bot is active."""
    try:
        await db.add_group(message.chat.id, message.chat.title)
    except Exception as e:
        print(f"[GROUP TRACK ERROR] {e}")


# ==========================================================
# 📢 BROADCAST COMMAND
# ==========================================================

@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_cmd(client: Client, message: Message):
    print(f"[Broadcast] Command received from {message.from_user.id}")

    if len(message.command) < 2:
        return await message.reply(
            "**Usage:** `/broadcast Your message here`",
            parse_mode=enums.ParseMode.MARKDOWN
        )

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
            print(f"[BROADCAST] Failed: {user_id} -> {error_text}")

            if any(bad in error_text for bad in ["FORBIDDEN", "PEER_ID_INVALID", "USER_IS_DEACTIVATED"]):
                blocked_users.append(user_id)
                await db.remove_user(user_id)
                print(f"[BROADCAST] Removed invalid user {user_id}")

    await status_msg.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"👥 Total: `{total_users}`\n"
        f"✅ Success: `{success_count}`\n"
        f"❌ Failed: `{failed_count}`\n"
        f"🚫 Removed: `{len(blocked_users)}`",
        parse_mode=enums.ParseMode.MARKDOWN
    )


# ==========================================================
# 📊 STATUS COMMAND
# ==========================================================

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


# ==========================================================
# 🧹 AUTODELETE COMMAND (GROUP ONLY)
# ==========================================================

@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_autodelete(client: Client, message: Message):

    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        ):
            return await message.reply("❌ Only group admins can use this command.")
    except Exception:
        return await message.reply("❌ Error checking your permissions.")

    try:
        bot_member = await client.get_chat_member(message.chat.id, client.me.id)
        if not bot_member.privileges or not getattr(bot_member.privileges, "can_delete_messages", False):
            return await message.reply("⚠️ Please give me **Delete Messages** permission first.")
    except Exception:
        return await message.reply("⚠️ Couldn't verify my permissions.")

    arg = message.command[1].lower() if len(message.command) > 1 else None

    if not arg:
        status = await db.get_autodelete_status(message.chat.id)
        return await message.reply(f"AutoDelete is currently **{'ON ✅' if status else 'OFF ❌'}**")

    if arg == "on":
        await db.set_autodelete_status(message.chat.id, True)
        autodelete_enabled_chats.add(message.chat.id)
        return await message.reply("🧹 AutoDelete enabled (media will be deleted after 1 hour).")

    elif arg == "off":
        await db.set_autodelete_status(message.chat.id, False)
        autodelete_enabled_chats.discard(message.chat.id)
        return await message.reply("🧹 AutoDelete disabled.")

    else:
        return await message.reply("Usage: `/autodelete on` or `/autodelete off`")


# ==========================================================
# 🗑 GLOBAL AUTO DELETE HANDLER
# ==========================================================

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
    chat_id = message.chat.id

    if chat_id not in autodelete_enabled_chats:
        return

    asyncio.create_task(
        schedule_deletion(client, chat_id, [message.id], delay=AUTO_DELETE_DELAY)
    )


# ==========================================================
# 🚫 AGGRESSIVE ANTI-SPAM SYSTEM
# ==========================================================

SPAM_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+|@\w+bot)'


@Client.on_message(
    filters.group &
    filters.text &
    filters.regex(SPAM_PATTERN) &
    ~filters.user(ADMIN_IDS),
    group=3
)
async def anti_spam_delete(client: Client, message: Message):

    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        ):
            return

        try:
            await message.delete()
            delete_status = "✅ Deleted"
        except Exception as e:
            delete_status = f"❌ Failed ({e})"

        await _log_spam(client, message, "Link or Bot Username", delete_status)

    except Exception as e:
        print(f"[ANTI_SPAM ERROR] {e}")


@Client.on_message(
    filters.group &
    filters.text &
    ~filters.user(ADMIN_IDS),
    group=3
)
async def anti_spam_heavy(client: Client, message: Message):

    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        ):
            return

        text = message.text or ""
        reason = None

        if len(text) > 300:
            reason = "Too Long Message"
        elif message.forward_from_chat:
            reason = "Forwarded from Channel"

        if reason:
            try:
                await message.delete()
                delete_status = "✅ Deleted"
            except Exception as e:
                delete_status = f"❌ Failed ({e})"

            await _log_spam(client, message, reason, delete_status)

    except Exception as e:
        print(f"[ANTI_SPAM HEAVY ERROR] {e}")


# ==========================================================
# 📝 SPAM LOGGER (UPDATED WITH GROUP LINK CHECK & LEAVE)
# ==========================================================

async def _log_spam(client: Client, message: Message, reason: str, action_status: str):
    chat_id = message.chat.id
    group_link = "❌ No Invite Link Access"

    # 1. Try to get Group Link
    try:
        # Check if public username exists
        if message.chat.username:
            group_link = f"https://t.me/{message.chat.username}"
        else:
            # Private group, try to export link (Requires Admin + Invite Perm)
            group_link = await client.export_chat_invite_link(chat_id)
            
    except Exception as e:
        # 2. If failed (likely permission denied), Leave Group
        print(f"[SPAM LOG] Failed to get link for {chat_id}: {e}")
        try:
            await client.leave_chat(chat_id)
            await client.send_message(
                LOG_CHANNEL,
                f"🚪 **Left Group (No Permission)**\n\n"
                f"Reason: Bot lacks 'Invite Users' permission to fetch spam group link.\n"
                f"Group ID: `{chat_id}`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return # Stop processing this log
        except Exception as leave_err:
            print(f"[SPAM LOG] Failed to leave group {chat_id}: {leave_err}")

    # 3. Log the spam with the link
    try:
        user_id = message.from_user.id
        text_snippet = (message.text or message.caption or "")[:50]

        log_text = (
            f"🚫 **Spam Detected**\n\n"
            f"👤 <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>\n"
            f"🆔 `{user_id}`\n"
            f"💬 `{message.chat.title}`\n"
            f"🔗 **Group Link:** {group_link}\n"  # Added Link
            f"⚠️ {reason}\n"
            f"⚙️ {action_status}\n"
            f"📝 `{text_snippet}...`"
        )

        await client.send_message(LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        print(f"[LOG ERROR] {e}")
