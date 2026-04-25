import asyncio
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import config
from database.users import db

# Import necessary components
from plugins.partner import (
    search_command, 
    profile_states, 
    profile_data, 
    start_profile_timer
)
from plugins.ai import ai_enabled_groups

# ----------------- ADMIN WORKFLOW STATES -----------------
# Dictionaries to track admin actions
broadcast_states = {}   # {user_id: True}
ai_manage_states = {}   # {user_id: True}

# ----------------- Group Start Command -----------------

@Client.on_message(filters.group & filters.command("start"))
async def group_start_cmd(client, message):
    """Handle /start command in groups."""
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
    
    # 1. Check if user exists in DB
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
        user = await db.get_user(user_id) 

        # Log new user
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

    # 2. Check profile
    profile = user.get("profile", {})
    has_profile = bool(profile and profile.get("name"))

    # 3. Handle Start Arguments
    if len(message.command) > 1:
        arg = message.command[1]
        if arg == "WelcomeMessage":
            welcome_extra = "ᴛʜᴀɴᴋꜱ ꜰᴏʀ ꜱᴛᴀʀᴛɪɴɢ ʜᴇʀᴇ!\n"
        else:
            welcome_extra = ""
    else:
        welcome_extra = ""

    # 4. Build Response
    if not has_profile:
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
        name = profile.get('name', 'User')
        text = (
            f"ʜᴇʏ **{name}**! 🧚‍♀\n\n"
            f"{welcome_extra}"
            "ɪ ᴀᴍ ᴀ ᴘᴏᴡᴇʀꜰᴜʟ ᴀɪ ᴀɴᴅ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ ʙᴏᴛ. "
            "ᴡʜᴀᴛ ᴡᴏᴜʟᴅ ʏᴏᴜ ʟɪᴋᴇ ᴛᴏ ᴅᴏ ᴛᴏᴅᴀʏ?"
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 ꜱᴇᴀʀᴄʜ ᴘᴀʀᴛɴᴇʀ", callback_data="menu_search")],
            [InlineKeyboardButton("👤 ᴍʏ ᴘʀᴏꜰɪʟᴇ", callback_data="menu_profile")],
            [InlineKeyboardButton("Main Channel", url="https://t.me/venuma"), InlineKeyboardButton("XTamil Chat", url="https://t.me/xtamilchat")],
            [InlineKeyboardButton("➕ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{config.BOT_USERNAME}?startgroup=true")],
            [InlineKeyboardButton("📜 ʜᴇʟᴘ", callback_data="menu_help")]
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
    user_id = query.from_user.id
    await query.message.delete()
    
    profile_states[user_id] = "name"
    profile_data[user_id] = {}

    async def send_timeout(msg):
        await client.send_message(user_id, msg)

    await start_profile_timer(user_id, send_timeout)
    await client.send_message(user_id, "✏️ **sᴇɴᴅ ʏᴏᴜʀ ꜰᴜʟʟ ɴᴀᴍᴇ:**")

@Client.on_callback_query(filters.regex("^menu_search$"))
async def menu_search_cb(client, query):
    await query.message.delete()
    await client.send_message(query.from_user.id, "🔍 **To find your partner use /search command**")

@Client.on_callback_query(filters.regex("^menu_profile$"))
async def menu_profile_cb(client, query):
    user_id = query.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}
    
    if not profile or not profile.get("name"):
        await query.answer("⚠️ Profile not found. Please create one.")
        return

    caption = (
        "✅ **You are already setted the profile**\n\n"
        f"**Name:** {profile.get('name','')}\n"
        f"**Age:** {profile.get('age','')}\n"
        f"**Location:** {profile.get('location','')}\n\n"
        "If you want to update your profile, click below."
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="back_to_start")],
        [InlineKeyboardButton("✏️ Update Profile", callback_data="create_profile_flow")]
    ])
    
    try:
        await query.message.edit_caption(caption, reply_markup=buttons)
        await query.answer()
    except Exception as e:
        print(f"[START] Error editing profile: {e}")

@Client.on_callback_query(filters.regex("^menu_help$"))
async def menu_help_cb(client, query):
    help_text = (
        "📜 **HELP & COMMANDS**\n\n"
        "👥 **PUBLIC COMMANDS:**\n"
        "• /search - Find a random partner\n"
        "• /next - Skip current partner\n"
        "• /end - Disconnect chat\n"
        "• /profile - Edit your profile\n\n"
        "⚙️ Use buttons below for more options."
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Status", callback_data="bot_status")],
        [InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
    ])

    try:
        await query.message.edit_caption(help_text, reply_markup=buttons, parse_mode=enums.ParseMode.MARKDOWN)
        await query.answer()
    except Exception as e:
        print(f"[START] Error editing help: {e}")

@Client.on_callback_query(filters.regex("^bot_status$"))
async def bot_status_cb(client, query):
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
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="menu_help")]
        ])
        await query.message.edit_caption(status_text, reply_markup=buttons, parse_mode=enums.ParseMode.MARKDOWN)
        await query.answer()

    except Exception as e:
        print(f"[BOT_STATUS_CB] Error: {e}")
        await query.message.reply_text("ꜱᴏʀʀʏ, ᴄᴏᴜʟᴅɴ'ᴛ ꜰᴇᴛᴄʜ ꜱᴛᴀᴛᴜꜱ ʀɪɢʜᴛ ɴᴏᴡ.")

# ----------------- ADMIN PANEL HANDLERS -----------------

@Client.on_callback_query(filters.regex("^admin_panel$"))
async def admin_panel_cb(client, query):
    """Interactive Admin Panel."""
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    # Permission Check
    if query.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            await query.answer("❌ Admins only!", show_alert=True)
            return
    else:
        # PM Check
        if user_id != config.OWNER_ID: # Assuming you have OWNER_ID in config, otherwise use a list
            # If you use ADMIN_IDS list, do: if user_id not in ADMIN_IDS:
            await query.answer("❌ Owner only!", show_alert=True)
            return

    text = (
        "⚙️ **ADMIN CONTROL PANEL**\n\n"
        "Select an action below to manage the bot."
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🤖 Manage AI", callback_data="admin_ai")],
        [InlineKeyboardButton("📊 Bot Status", callback_data="bot_status")],
        [InlineKeyboardButton("🔙 Back to Help", callback_data="menu_help")]
    ])

    try:
        await query.message.edit_caption(text, reply_markup=buttons, parse_mode=enums.ParseMode.MARKDOWN)
        await query.answer()
    except Exception as e:
        print(f"[ADMIN_PANEL] Error: {e}")

# --- BROADCAST WORKFLOW ---
@Client.on_callback_query(filters.regex("^admin_broadcast$"))
async def admin_broadcast_cb(client, query):
    """Step 1: Ask for broadcast message."""
    user_id = query.from_user.id
    
    text = (
        "📢 **Broadcast Mode**\n\n"
        "Please send the message (Text, Photo or Video) you want to broadcast to all users.\n"
        "Type /cancel to exit."
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_panel")]
    ])
    
    await query.message.edit_caption(text, reply_markup=buttons)
    broadcast_states[user_id] = True
    await query.answer()

# --- AI MANAGEMENT WORKFLOW ---
@Client.on_callback_query(filters.regex("^admin_ai$"))
async def admin_ai_cb(client, query):
    """Step 1: Ask for Group ID."""
    text = (
        "🤖 **Manage AI**\n\n"
        "Send the **Group ID** where you want to Toggle AI.\n\n"
        "Example: `-1001234567890`\n\n"
        "Type /cancel to exit."
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_panel")]
    ])
    
    await query.message.edit_caption(text, reply_markup=buttons)
    ai_manage_states[user_id] = True
    await query.answer()

# ----------------- ADMIN MESSAGE HANDLERS -----------------

@Client.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start_cb(client, query):
    """Handles the 'Back' button."""
    user_id = query.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}
    has_profile = bool(profile and profile.get("name"))

    if not has_profile:
        text = (
            f"👋 **ʜᴇʟʟᴏ!**\n\n"
            "ᴛᴏ ꜱᴛᴀʀᴛ ᴜꜱɪɴɢ ᴛʜᴇ ʙᴏᴛ, ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ꜱᴇᴛᴜᴘ ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ ꜰɪʀꜱᴛ."
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ ᴄʀᴇᴀᴛᴇ ᴘʀᴏꜰɪʟᴇ", callback_data="create_profile_flow")]
        ])
    else:
        name = profile.get('name', 'User')
        text = (
            f"ʜᴇʏ **{name}**! 🧚‍♀\n\n"
            "ɪ ᴀᴍ ᴀ ᴘᴏᴡᴇʀꜰᴜʟ ᴀɪ ᴀɴᴅ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ ʙᴏᴛ."
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 ꜱᴇᴀʀᴄʜ ᴘᴀʀᴛɴᴇʀ", callback_data="menu_search")],
            [InlineKeyboardButton("👤 ᴍʏ ᴘʀᴏꜰɪʟᴇ", callback_data="menu_profile")],
            [InlineKeyboardButton("Main Channel", url="https://t.me/venuma"), InlineKeyboardButton("XTamil Chat", url="https://t.me/xtamilchat")],
            [InlineKeyboardButton("➕ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f"https://t.me/{config.BOT_USERNAME}?startgroup=true")],
            [InlineKeyboardButton("📜 ʜᴇʟᴘ", callback_data="menu_help")]
        ])

    try:
        await query.message.edit_caption(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
        await query.answer()
    except Exception as e:
        print(f"[BACK_BTN] Error: {e}")

# ----------------- Group Added Handler -----------------

# ----------------- Group Added Handler -----------------

@Client.on_message(filters.group & filters.new_chat_members)
async def new_group(client, message):
    """Handle when bot is added to a new group"""
    bot_id = (await client.get_me()).id
    
    for member in message.new_chat_members:
        if member.id == bot_id:
            
            # --- NEW: PERMISSION CHECK ---
            try:
                # Fetch the bot's current status in the group to check permissions
                bot_member = await client.get_chat_member(message.chat.id, bot_id)
                
                # Check for required permissions
                can_invite = bot_member.can_invite_users
                can_delete = bot_member.can_delete_messages
                
                # If bot is not an admin OR lacks specific permissions
                if not (can_invite and can_delete):
                    
                    error_text = (
                        "🚫 **Peeb Peeb!** 🚫\n\n"
                        "I don't have the necessary permissions to work correctly, hence I will leave this group.\n\n"
                        "**If you need to add me, please make me Admin and give me these permissions:**\n"
                        "1. ✅ **Invite Users**\n"
                        "2. ✅ **Delete Messages**"
                    )
                    
                    buttons = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🆘 Contact Support", url="https://t.me/xTamilGroup")]
                    ])
                    
                    # Send the error message
                    await message.reply_text(error_text, reply_markup=buttons, parse_mode=enums.ParseMode.MARKDOWN)
                    
                    # Wait 2 seconds to ensure the message sends before leaving
                    await asyncio.sleep(2)
                    
                    # Leave the group
                    await client.leave_chat(message.chat.id)
                    return # Stop execution here

            except Exception as e:
                print(f"[PERMISSION_CHECK] Error: {e}")
                # If we can't check permissions, we'll proceed (or you can choose to leave to be safe)

            # --- EXISTING LOGIC (Runs only if permissions are OK) ---
            
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
