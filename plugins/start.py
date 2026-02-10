# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import config
from database.users import db

# Import necessary components from partner to handle the flow
from plugins.partner import (
    search_command, 
    profile_states, 
    profile_data, 
    start_profile_timer
)
from plugins.ai import ai_enabled_groups

# ----------------- Group Start Command -----------------

@Client.on_message(filters.group & filters.command("start"))
async def group_start_cmd(client, message):
    """Handle /start command in groups using config username for speed."""
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Start in PM", url=f"https://t.me/{config.BOT_USERNAME}?start=WelcomeMessage")]
    ])
    await message.reply_text(
        "ʏᴏᴜ ᴄᴀɴɴᴏᴛ ꜱᴛᴀʀᴛ ᴍᴇ ɪɴ ᴀ ɢʀᴏᴜᴘ. ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴜꜱᴇ ᴍᴇ ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ.",
        reply_markup=buttons
    )

# ----------------- Private Start Command -----------------

@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    """UNIFIED START COMMAND with Profile Check."""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Unknown"
    
    # 1. Check if user exists in DB, if not, add and log
    user = await db.get_user(user_id)
    is_new_user = False

    if not user:  
        await db.add_user(user_id, {
            "name": "",
            "gender": "",
            "age": None,
            "location": "",
            "dp": None
        }, user_type="user")
        is_new_user = True
        user = await db.get_user(user_id) # Refresh user object

        # Log new user to channel
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

    # 2. Check if user has a complete profile
    profile = user.get("profile", {})
    has_profile = bool(profile and profile.get("name"))

    # 3. Handle Start Arguments (e.g., from group button)
    if len(message.command) > 1:
        arg = message.command[1]
        if arg == "WelcomeMessage":
            welcome_extra = "ᴛʜᴀɴᴋꜱ ꜰᴏʀ ꜱᴛᴀʀᴛɪɴɢ ʜᴇʀᴇ!\n"
        else:
            welcome_extra = ""
    else:
        welcome_extra = ""

    # 4. Build Response based on Profile Status
    if not has_profile:
        # --- USER NEEDS PROFILE ---
        text = (
            f"👋 **ʜᴇʟʟᴏ {first_name}!**\n\n"
            f"{welcome_extra}"
            "ᴛᴏ ꜱᴛᴀʀᴛ ᴜꜱɪɴɢ ᴛʜᴇ ʙᴏᴛ, ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ꜱᴇᴛᴜᴘ ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ ꜰɪʀꜱᴛ.\n"
            "ᴛʜɪꜱ ʜᴇʟᴘꜱ ᴜꜱ ꜰɪɴᴅ ʏᴏᴜ ᴀ ᴍᴀᴛᴄʜ ʙᴀꜱᴇᴅ ᴏɴ ʏᴏᴜʀ ᴅᴇᴛᴀɪʟꜱ."
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ ᴄʀᴇᴀᴛᴇ ᴘʀᴏꜰɪʟᴇ", callback_data="create_profile_flow")]
        ])
        await message.reply_photo(
            photo="https://graph.org/file/c3be33fb5c2a81a835292-2c39b4021db14d2a69.jpg",
            caption=text,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML
        )
    
    else:
        # --- USER HAS PROFILE (Show Menu) ---
        name = profile.get('name', 'User')
        
        text = (
            f"ʜᴇʏ **{name}**! 🧚‍♀\n\n"
            f"{welcome_extra}"
            "ɪ ᴀᴍ ᴀ ᴘᴏᴡᴇʀꜰᴜʟ ᴀɪ ᴀɴᴅ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ ʙᴏᴛ. "
            "ᴡʜᴀᴛ ᴡᴏᴜʟᴅ ʏᴏᴜ ʟɪᴋᴇ ᴛᴏ ᴅᴏ ᴛᴏᴅᴀʏ?"
        )
        
        buttons = InlineKeyboardMarkup([
            # Row 1: Main Actions
            [
                InlineKeyboardButton("🔍 ꜱᴇᴀʀᴄʜ ᴘᴀʀᴛɴᴇʀ", callback_data="menu_search"),
                InlineKeyboardButton("👤 ᴍʏ ᴘʀᴏꜰɪʟᴇ", callback_data="menu_profile")
            ],
            # Row 2: External Links
            [
                InlineKeyboardButton("Main Channel", url="https://t.me/venuma"),
                InlineKeyboardButton("XTamil Chat", url="https://t.me/xtamilchat")
            ],
            # Row 3: Add to Group & Help
            [
                InlineKeyboardButton("➕ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{config.BOT_USERNAME}?startgroup=true"),
                InlineKeyboardButton("📜 ʜᴇʟᴘ", callback_data="menu_help")
            ]
        ])
        
        await message.reply_photo(
            photo="https://graph.org/file/c3be33fb5c2a81a835292-2c39b4021db14d2a69.jpg",
            caption=text,
            reply_markup=buttons,
            parse_mode=enums.ParseMode.HTML
        )


# ----------------- Callback Handlers -----------------

@Client.on_callback_query(filters.regex("^create_profile_flow$"))
async def create_profile_cb(client, query):
    """Handles the 'Create Profile' button click."""
    user_id = query.from_user.id
    await query.message.delete()
    
    # Initialize the profile state manually
    profile_states[user_id] = "name"
    profile_data[user_id] = {}

    async def send_timeout(msg):
        await client.send_message(user_id, msg)

    await start_profile_timer(user_id, send_timeout)
    await client.send_message(user_id, "✏️ **sᴇɴᴅ ʏᴏᴜʀ ꜰᴜʟʟ ɴᴀᴍᴇ:**")


@Client.on_callback_query(filters.regex("^menu_search$"))
async def menu_search_cb(client, query):
    """Handles the 'Search' button click."""
    await query.message.delete()
    # Trigger search by simulating a /search command
    await client.send_message(query.from_user.id, "/search")


@Client.on_callback_query(filters.regex("^menu_profile$"))
async def menu_profile_cb(client, query):
    """Handles the 'My Profile' button click."""
    await query.message.delete()
    await client.send_message(query.from_user.id, "/myprofile")


@Client.on_callback_query(filters.regex("^menu_help$"))
async def menu_help_cb(client, query):
    """Handles the 'Help' button click."""
    help_text = (
        "📜 **ʜᴇʟᴘ & ʀᴜʟᴇꜱ**\n\n"
        "🔍 **ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ:**\n"
        "• /search - ꜰɪɴᴅ ᴀ ᴘᴀʀᴛɴᴇʀ\n"
        "• /next - ꜱᴋɪᴘ ᴄᴜʀʀᴇɴᴛ ᴘᴀʀᴛɴᴇʀ\n"
        "• /end - ᴅɪꜱᴄᴏɴɴᴇᴄᴛ ᴄʜᴀᴛ\n"
        "• /profile - ᴇᴅɪᴛ ʏᴏᴜʀ ᴅᴇᴛᴀɪʟꜱ\n\n"
        "🤖 **ɢʀᴏᴜᴘ ᴀɪ:**\n"
        "• /ai on - ᴇɴᴀʙʟᴇ ᴀɪ (ᴀᴅᴍɪɴ)\n"
        "• /ai off - ᴅɪꜱᴀʙʟᴇ ᴀɪ (ᴀᴅᴍɪɴ)\n\n"
        "📝 **ʀᴜʟᴇꜱ:**\n"
        "1. ʙᴇ ʀᴇꜱᴘᴇᴄᴛꜰᴜʟ ᴛᴏ ᴏᴛʜᴇʀꜱ.\n"
        "2. ɴᴏ ꜱᴘᴀᴍᴍɪɴɢ ᴏʀ ɪʟʟᴇɢᴀʟ ᴄᴏɴᴛᴇɴᴛ."
    )
    
    # Added a Bot Status button in help menu
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ", callback_data="bot_status")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_to_start")]
    ])
    await query.message.edit_text(help_text, reply_markup=buttons)

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
            f"⚡ **ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ:** `ᴏɴʟɪɴᴇ`"
        )
        
        # Reuse the Back button
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="menu_help")]
        ])
        await query.message.edit_text(status_text, reply_markup=buttons, parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        print(f"[BOT_STATUS_CB] Error fetching status: {e}")
        await query.message.reply_text("ꜱᴏʀʀʏ, ᴄᴏᴜʟᴅɴ'ᴛ ꜰᴇᴛᴄʜ ꜱᴛᴀᴛᴜꜱ ʀɪɢʜᴛ ɴᴏᴡ.")

@Client.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start_cb(client, query):
    """Handles the 'Back' button."""
    await query.message.delete()
    await client.send_message(query.from_user.id, "/start")


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
