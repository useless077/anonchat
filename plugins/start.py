# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import config
from database.users import db
from plugins.partner import search_command
from plugins.ai import ai_enabled_groups

# ----------------- Commands -----------------

@Client.on_message(filters.group & filters.command("start"))
async def group_start_cmd(client, message):
    """Handle /start command in groups"""
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Start in PM", url=f"https://t.me/{(await client.get_me()).username}")]
    ])
    await message.reply_text(
        "ʏᴏᴜ ᴄᴀɴɴᴏᴛ ꜱᴛᴀʀᴛ ᴍᴇ ɪɴ ᴀ ɢʀᴏᴜᴘ. ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴜꜱᴇ ᴍᴇ ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ.",
        reply_markup=buttons
    )

@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    """UNIFIED START COMMAND for private chats."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Unknown"

    # Check user in DB
    user = await db.get_user(user_id)

    if not user:  # First time user
        await db.add_user(user_id, {
            "name": "",
            "gender": "",
            "age": None,
            "location": "",
            "dp": None
        }, user_type="user")

        # Log to channel
        try:
            username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
            log_text = (
                f"🆕 **New User Joined**\n\n"
                f"👤 **User:** <a href='tg://user?id={user_id}'>{first_name}</a>\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"📝 **Username:** {username}"
            )
        
            await client.send_message(
                config.LOG_CHANNEL,
                log_text,
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            print(f"[LOG ERROR] Could not send to log channel: {e}")

    # Get Bot Username dynamically for the "Add to Group" link
    me = await client.get_me()
    bot_username = me.username if me.username else "venumabot"

    welcome_text = (
        "👋 **ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴏᴜʀ ᴘᴏᴡᴇʀꜰᴜʟ ᴄʜᴀᴛ ʙᴏᴛ!**\n\n"
        "ɪ ᴀᴍ ᴍᴏʀᴇ ᴛʜᴀɴ ᴊᴜꜱᴛ ᴀɴ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ ʙᴏᴛ. ɪ ᴀᴍ ᴀ ᴘᴏᴡᴇʀꜰᴜʟ ᴀɪ ᴄʜᴀᴛ ʙᴏᴛ ᴛᴏᴏ!\n\n"
        "🔍 **ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ ꜰᴇᴀᴛᴜʀᴇꜱ:**\n"
        "• /profile - ᴄʀᴇᴀᴛᴇ ᴏʀ ᴜᴘᴅᴀᴛᴇ ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ\n"
        "• /search - ꜰɪɴᴅ ᴀ ʀᴀɴᴅᴏᴍ ᴘᴀʀᴛɴᴇʀ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ\n"
        "• /cancel - ᴄᴀɴᴄᴇʟ ʏᴏᴜʀ ᴘᴀʀᴛɴᴇʀ ꜱᴇᴀʀᴄʜ\n"
        "• /myprofile - ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴜʀʀᴇɴᴛ ᴘʀᴏꜰɪʟᴇ\n"
        "• /next - ꜱᴋɪᴘ ᴛᴏ ᴛʜᴇ ɴᴇxᴛ ᴘᴀʀᴛɴᴇʀ\n"
        "• /end - ᴇɴᴅ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴄʜᴀᴛ\n\n"
        "🤖 **ᴀɪ ɢʀᴏᴜᴘ ꜰᴇᴀᴛᴜʀᴇꜱ:**\n"
        "• ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ\n"
        "• ᴜꜱᴇ '/ai on` ᴛᴏ ᴀᴄᴛɪᴠᴀᴛᴇ ᴍᴇ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ)\n"
        "• ɪ ᴡɪʟʟ ᴄʜᴀᴛ ɴᴀᴛᴜʀᴀʟʟʏ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ!"
    )

    # --- UPDATED BUTTONS LAYOUT ---
    buttons = InlineKeyboardMarkup([
        # Row 1: Main Channel and XTamil Chat
        [
            InlineKeyboardButton("Main Channel", url="https://t.me/venuma"),
            InlineKeyboardButton("XTamil Chat", url="https://t.me/xtamilchat")
        ],
        # Row 2: Add to Group
        [
            InlineKeyboardButton("➕ Add to Your Group", url=f"https://t.me/{bot_username}?startgroup=true")
        ],
        # Row 3: Find Your Partner
        [
            InlineKeyboardButton("🔍 Find Your Partner", callback_data="search")
        ]
    ])

    await message.reply_photo(
        photo="https://graph.org/file/c3be33fb5c2a81a835292-2c39b4021db14d2a69.jpg",
        caption=welcome_text,
        reply_markup=buttons,
        parse_mode=enums.ParseMode.HTML
    )

# ----------------- Callback Handlers -----------------
@Client.on_callback_query(filters.regex("^search$"))
async def search_cb(client, query):
    await query.answer()
    # Call search_command directly. This will start the search process.
    await search_command(client, query.message)

@Client.on_callback_query(filters.regex("^bot_status$"))
async def bot_status_cb(client, query):
    """Handles the 'Bot Status' button click."""
    await query.answer()
    
    try:
        total_users = await db.get_total_users()
        active_chats = await db.get_active_chats()
        ai_groups = len(ai_enabled_groups)
        total_groups = await db.get_total_groups()
        
        status_text = (
            f"🤖 **ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ**\n\n"
            f"👥 **ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:** `{total_users}`\n"
            f"💬 **ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛꜱ:** `{active_chats}`\n"
            f"🤖 **ᴀɪ ᴇɴᴀʙʟᴇᴅ ɢʀᴏᴜᴘꜱ:** `{ai_groups}`\n"
            f"🌐 **ᴛᴏᴛᴀʟ ɢʀᴏᴜᴘꜱ:** `{total_groups}`\n\n"
            f"⚡ **ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ:** `ᴏɴʟɪɴᴇ ᴀɴᴅ ᴡᴏʀᴋɪɴɢ`"
        )
        
        await query.message.reply_text(status_text, parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        print(f"[BOT_STATUS_CB] Error fetching status: {e}")
        await query.message.reply_text("ꜱᴏʀʀʏ, ᴄᴏᴜʟᴅɴ'ᴛ ꜰᴇᴛᴄʜ ᴛʜᴇ ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ ʀɪɢʜᴛ ɴᴏᴡ.")


# ----------------- Group Added Handler -----------------
@Client.on_message(filters.group & filters.new_chat_members)
async def new_group(client, message):
    """Handle when bot is added to a new group"""
    bot_id = (await client.get_me()).id
    
    for member in message.new_chat_members:
        if member.id == bot_id:
            await db.add_user(message.chat.id, {"title": message.chat.title}, user_type="group")

            try:
                chat = message.chat
                log_text = (
                    f"🆕 **Bot Added to New Group**\n\n"
                    f"📝 **Group Name:** {chat.title}\n"
                    f"🆔 **Group ID:** `{chat.id}`\n"
                    f"👤 **Added by:** <a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>\n"
                    f"🆔 **User ID:** `{message.from_user.id}`"
                )
                
                await client.send_message(
                    config.LOG_CHANNEL,
                    log_text,
                    parse_mode=enums.ParseMode.HTML
                )
                
                welcome_msg = (
                    "👋 **ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ ᴛᴏ ᴛʜɪꜱ ɢʀᴏᴜᴘ!**\n\n"
                    "🤖 **ɪ'ᴍ ᴀ ᴘᴏᴡᴇʀꜰᴜʟ ᴀɪ ᴄʜᴀᴛ ʙᴏᴛ ᴛʜᴀᴛ ᴄᴀɴ ᴀɴꜱᴡᴇʀ ʏᴏᴜʀ Qᴜᴇꜱᴛɪᴏɴꜱ ᴀɴᴅ ʜᴀᴠᴇ ᴄᴏɴᴠᴇʀꜱᴀᴛɪᴏɴꜱ ᴡɪᴛʜ ʏᴏᴜ.**\n\n"
                    "📋 **ᴄᴏᴍᴍᴀɴᴅꜱ:**\n"
                    "• `/ai on` - ᴇɴᴀʙʟᴇ ᴀɪ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ)\n"
                    "• `/ai off` - ᴅɪꜱᴀʙʟᴇ ᴀɪ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ)\n\n"
                    "💡 **ʜᴏᴡ ᴛᴏ ᴜꜱᴇ:**\n"
                    "1. ᴇɴᴀʙʟᴇ ᴀɪ ᴡɪᴛʜ `/ai on`\n"
                    "2. ᴍᴇɴᴛɪᴏɴ ᴍᴇ ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴍʏ ᴍᴇꜱꜱᴀɢᴇꜱ\n"
                    "3. ɪ'ʟʟ ʀᴇꜱᴘᴏɴᴅ ᴡɪᴛʜ ɪɴᴛᴇʟʟɪɢᴇɴᴛ ᴀɴꜱᴡᴇʀꜱ!"
                )
                await message.reply_text(welcome_msg, parse_mode=enums.ParseMode.HTML)
            except Exception as e:
                print(f"[GROUP_ADDED] Error: {e}")
            break
