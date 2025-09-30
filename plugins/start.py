# plugins/start.py
import asyncio
import random  # <-- ADD THIS
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import config   # for LOG_CHANNEL
from utils import (    
    add_user,
    remove_user,
    set_partner,
    update_activity,
    sessions,
    start_profile_timer,
    log_message,
)
from database.users import db


# state holders
profile_states = {}
profile_data = {}
profile_timeouts = {}
waiting_users = set()
waiting_lock = asyncio.Lock()
search_flood = {} # user_id -> datetime of last search

CONNECTION_EMOJIS = ["🎉", "🥳", "🎊", "✨", "🤝", "💫", "🌟", "🎈"]
REACTION_EMOJIS = ["👍", "👌", "❤️", "🥰", "😊", "✅", "👏", "😍"]
CONNECTION_STICKER_ID = "CAACAgUAAyEFAASH239qAAPmaNu1X46I2IKBOBtfNH3ot9jO0MsAAmIaAAKEFOBWbLL49T60Z7QeBA" # Example "Hi" sticker

# ----------------- Commands -----------------

@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Unknown"

    # Check if user already exists
    user = await db.get_user(user_id)
    is_new = user is None

    # Add / update user
    add_user(user_id)

    if not user or not user.get("profile"):
        await db.add_user(user_id, {"name": "", "gender": "", "age": None, "location": "", "dp": None})

    # New, cleaner welcome message
    welcome_text = (
        "👋 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴏᴜʀ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀᴛ ʙᴏᴛ!\n\n"
        "ᴜꜱᴇ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅꜱ ʙᴇʟᴏᴡ ᴛᴏ ꜱᴛᴀʀᴛ ᴄʜᴀᴛᴛɪɴɢ:\n"
        "• `/profile` - ᴄʀᴇᴀᴛᴇ ᴏʀ ᴜᴘᴅᴀᴛᴇ ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ\n"
        "• `/search` - ꜰɪɴᴅ ᴀ ʀᴀɴᴅᴏᴍ ᴘᴀʀᴛɴᴇʀ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ\n"
        "• `/myprofile` - ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴜʀʀᴇɴᴛ ᴘʀᴏꜰɪʟᴇ\n"
        "• `/next` - ꜱᴋɪᴘ ᴛᴏ ᴛʜᴇ ɴᴇxᴛ ᴘᴀʀᴛɴᴇʀ\n"
        "• `/end` - ᴇɴᴅ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴄʜᴀᴛ"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join our channel", url="https://t.me/venuma")],
        [InlineKeyboardButton("🔍 Search Partner", callback_data="search")]
    ])
    
    await message.reply_photo(
        photo="https://graph.org/file/c3be33fb5c2a81a835292-2c39b4021db14d2a69.jpg",
        caption=welcome_text,
        reply_markup=buttons
    )

    # Log only if new user
    if is_new:
        try:
            await client.send_message(
                config.LOG_CHANNEL,
                f"🆕 **New User Joined**\n"
                f"👤 ID: `{user_id}`\n"
                f"📛 Name: {first_name}"
            )
        except Exception as e:
            print(f"[LOG ERROR] Could not send to log channel: {e}")

# ----------------- Callback Handlers -----------------
@Client.on_callback_query(filters.regex("^search$"))
async def search_cb(client, query):
    """Handles the 'Search Partner' button click."""
    # --- NEW: Debug print to see if this function is even called ---
    print(f"[CALLBACK] search_cb called for user {query.from_user.id}")

    await query.answer()
        
    class FakeMessage:
        def __init__(self, from_user):
            self.from_user = from_user

    fake_message = FakeMessage(query.from_user)
    await search_command(client, fake_message)

@Client.on_callback_query(filters.regex("^profile$"))
async def profile_cb(client, query):
    """Handles the 'Update Profile' button click."""
    await query.answer()
    message = Message._from_client(
        client,
        {
            "message_id": query.message.message_id,
            "from": query.from_user,
            "date": query.message.date,
            "chat": query.message.chat
        }
    )
    await profile_cmd(client, message)


# ----------------- Profile -----------------
@Client.on_message(filters.private & filters.command("profile"))
async def profile_cmd(client, message):
    user_id = message.from_user.id
    profile_states[user_id] = "name"
    profile_data[user_id] = {}

    async def send_timeout(msg):
        await client.send_message(user_id, msg)

    await start_profile_timer(user_id, send_timeout)
    await message.reply_text("✏️ Send your full name:")
    
@Client.on_callback_query(filters.regex("^gender_"))
async def gender_cb(client, query):
    user_id = query.from_user.id
    gender = query.data.split("_")[1]
    profile_data[user_id]["gender"] = gender
    profile_states[user_id] = "age"
    await query.answer(f"✅ Gender '{gender}' selected")
    await query.message.reply_text("Now send your age (10-99):")

@Client.on_message(
    filters.private & 
    ~filters.command(["start","profile","search","next","end","myprofile"]) &
    filters.create(lambda _, __, message: message.from_user.id in profile_states)
)
async def profile_steps(client, message):
    print(f"[DEBUG] profile_steps handler called for user {message.from_user.id}")
    
    user_id = message.from_user.id
    
    if user_id not in profile_states: 
        return
        
    profile_timeouts[user_id] = datetime.utcnow()
    step = profile_states[user_id]
    
    if not message.text and step in ["name", "age", "location"]:
        await message.reply_text("❌ Please send only **text** input for your profile details (Name, Age, Location).")
        return

    text = message.text.strip()
    
    if step == "name":
        profile_data[user_id]["name"] = text
        profile_states[user_id] = "gender"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Male", callback_data="gender_male")],
            [InlineKeyboardButton("Female", callback_data="gender_female")],
            [InlineKeyboardButton("Shemale", callback_data="gender_shemale")]
        ])
        await message.reply_text("✅ Name saved. Choose gender:", reply_markup=buttons)
    
    elif step == "age":
        if not text.isdigit() or not (10 <= int(text) <= 99):
            await message.reply_text("❌ Enter valid age (10-99)")
            return
        profile_data[user_id]["age"] = int(text)
        profile_states[user_id] = "location"
        await message.reply_text("✅ Age saved. Now send your location (city/country):")
    
    elif step == "location":
        profile_data[user_id]["location"] = text
        user = await db.get_user(user_id)
        profile = user.get("profile", {}) if user else {}
        profile.update(profile_data[user_id])
        await db.add_user(user_id, profile)
        
        profile_states.pop(user_id, None)
        profile_data.pop(user_id, None)
        profile_timeouts.pop(user_id, None)
        
        await message.reply_text("🎉 Profile updated successfully!")
    
    return

@Client.on_message(filters.private & filters.command("myprofile"))
async def myprofile_cmd(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}
    if not profile or not profile.get("gender"):
        await message.reply_text("⚠️ You have not set profile yet. Use /profile")
        return
    caption = f"👤 **ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ**\n\n"
    caption += f"• ɴᴀᴍᴇ: {profile.get('name','')}\n• ɢᴇɴᴅᴇʀ: {profile.get('gender','')}\n"
    caption += f"• ᴀɢᴇ: {profile.get('age','')}\n• ʟᴏᴄᴀᴛɪᴏɴ: {profile.get('location','')}\n"
    await message.reply_text(caption)

# ----------------- Search Partner -----------------
@Client.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    user_id = message.from_user.id
    # --- NEW: Anti-spam check ---
    # If the user has used /search in the last 3 seconds, ignore them.
    if user_id in search_flood and (datetime.utcnow() - search_flood[user_id]).total_seconds() < 3:
        print(f"[SEARCH] User {user_id} is spamming /search command. Ignoring.")
        return

    # Update the last time the user searched
    search_flood[user_id] = datetime.utcnow()
    print(f"[SEARCH] User {user_id} passed the anti-spam check. Proceeding.") # This print shows a new search is starting
    
    async with waiting_lock:
        if user_id in sessions:
            await message.reply_text("You are already in a chat. Use /end to leave first.")
            return
        if user_id in waiting_users:
            await message.reply_text("You are already searching for a partner... Please wait.")
            return

        waiting_users.add(user_id)
        await message.reply_text("🔍 Searching for a partner...")

        if len(waiting_users) > 1:
            user1_id = waiting_users.pop()
            user2_id = waiting_users.pop()

            try:
                set_partner(user1_id, user2_id)
                await db.set_partners_atomic(user1_id, user2_id)
                await db.update_status(user1_id, "chatting")
                await db.update_status(user2_id, "chatting")

                # --- NEW: Get full user objects for detailed logging ---
                user_objects = await client.get_users([user1_id, user2_id])
                user1_obj, user2_obj = user_objects[0], user_objects[1]

                # --- NEW: Send animated sticker first ---
                await client.send_sticker(user1_id, CONNECTION_STICKER_ID)
                await client.send_sticker(user2_id, CONNECTION_STICKER_ID)
                await asyncio.sleep(0.5) # Small delay for effect

                # --- NEW: Get random emojis for the message ---
                emojis = random.sample(REACTION_EMOJIS, 3) # <-- CHANGE HERE
                emoji_string = " ".join(emojis)

                # Get partner profiles from DB
                user1_db = await db.get_user(user1_id)
                user2_db = await db.get_user(user2_id)
                profile1 = user1_db.get("profile", {})
                profile2 = user2_db.get("profile", {})

                # --- NEW: Create detailed connection messages for users ---
                partner2_name = profile2.get("name", "Not found")
                partner2_age = profile2.get("age", "Not found")
                partner2_gender = profile2.get("gender", "Not found")
                text_for_user1 = (
                    f"{emoji_string}\n\n"
                    "🎉 ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! ʏᴏᴜ ᴀʀᴇ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴡɪᴛʜ ᴀ ᴘᴀʀᴛɴᴇʀ.\n\n"
                    "👤 **ᴘᴀʀᴛɴᴇʀ'ꜱ ᴅᴇᴛᴀɪʟꜱ:**\n"
                    f"• ɴᴀᴍᴇ: {partner2_name}\n"
                    f"• ᴀɢᴇ: {partner2_age}\n"
                    f"• ɢᴇɴᴅᴇʀ: {partner2_gender}\n\n"
                    "Say hi to start the conversation!"
                )

                partner1_name = profile1.get("name", "Not found")
                partner1_age = profile1.get("age", "Not found")
                partner1_gender = profile1.get("gender", "Not found")
                text_for_user2 = (
                    f"{emoji_string}\n\n"
                    "🎉 ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! ʏᴏᴜ ᴀʀᴇ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴡɪᴛʜ ᴀ ᴘᴀʀᴛɴᴇʀ.\n\n"
                    "👤 **ᴘᴀʀᴛɴᴇʀ'ꜱ ᴅᴇᴛᴀɪʟꜱ:**\n"
                    f"• ɴᴀᴍᴇ: {partner1_name}\n"
                    f"• ᴀɢᴇ: {partner1_age}\n"
                    f"• ɢᴇɴᴅᴇʀ: {partner1_gender}\n\n"
                    "Say hi to start the conversation!"
                )

                await client.send_message(user1_id, text_for_user1, parse_mode=enums.ParseMode.HTML)
                await client.send_message(user2_id, text_for_user2, parse_mode=enums.ParseMode.HTML)

                print(f"[SEARCH] Successfully paired {user1_id} with {user2_id}")

                # --- NEW: Create detailed log message for the LOG_CHANNEL ---
                def format_user_info(user):
                    username = f"@{user.username}" if user.username else "No Username"
                    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a> ({username}) `[ID: {user.id}]`"

                log_text = (
                    f"🤝 **New Pairing**\n\n"
                    f"👤 **User 1:** {format_user_info(user1_obj)}\n"
                    f"👤 **User 2:** {format_user_info(user2_obj)}"
                )

                async def log_pairing():
                    try:
                        await client.send_message(
                            config.LOG_CHANNEL,
                            log_text,
                            parse_mode=enums.ParseMode.HTML
                        )
                    except Exception as e:
                        print(f"[SEARCH] Failed to log pairing: {e}")
                
                client.loop.create_task(log_pairing())

            except Exception as e:
                print(f"[SEARCH] Error during pairing {user1_id} and {user2_id}: {e}")
                await client.send_message(user1_id, "❌ An error occurred. Please try searching again.")
                await client.send_message(user2_id, "❌ An error occurred. Please try searching again.")
                sessions.pop(user1_id, None)
                sessions.pop(user2_id, None)


# ----------------- Next / End -----------------
@Client.on_message(filters.private & filters.command("next"))
async def next_cmd(client, message):
    user_id = message.from_user.id
    partner_id = sessions.pop(user_id, None)

    if partner_id:
        sessions.pop(partner_id, None)
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)
        remove_user(user_id)
        remove_user(partner_id)

        await client.send_message(user_id, "🔄 Searching for next partner...")
        await client.send_message(partner_id, "❌ Your partner left.")
        await search_command(client, message)
    else:
        await search_command(client, message)


@Client.on_message(filters.private & filters.command("end"))
async def end_chat(client, message):
    user_id = message.from_user.id
    partner_id = sessions.get(user_id)
    if not partner_id:
        user = await db.get_user(user_id)
        partner_id = user.get("partner_id") if user else None

    if partner_id:
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        sessions.pop(user_id, None)
        sessions.pop(partner_id, None)
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)

        await client.send_message(user_id, "❌ You disconnected from the chat.")
        await client.send_message(partner_id, "❌ Your partner disconnected.")
    else:
        waiting_users.discard(user_id)
        sessions.pop(user_id, None)
        await db.update_status(user_id, "idle")
        await message.reply_text("⚠️ You are not connected to anyone.")


# ----------------- Relay Messages & Media -----------------
@Client.on_message(filters.private & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def relay_all(client: Client, message: Message):
    print(f"[DEBUG] relay_all handler called for user {message.from_user.id}")
    
    user_id = message.from_user.id

    if user_id in profile_states:
        print(f"[relay_all] {user_id} is in profile setup, ignoring message.")
        return

    print(f"[relay_all] Message from {user_id}")

    partner_id = sessions.get(user_id)

    if not partner_id:
        print(f"[relay_all] Partner not in session for {user_id}, checking DB...")
        user_db = await db.get_user(user_id)
        partner_id = user_db.get("partner_id") if user_db else None

        if partner_id:
            partner_user = await db.get_user(partner_id)
            if partner_user and partner_user.get("partner_id") == user_id:
                sessions[user_id] = partner_id
                sessions[partner_id] = user_id
                print(f"[relay_all] Partner {partner_id} restored from DB for {user_id}")
            else:
                print(f"[relay_all] Invalid partner {partner_id} found in DB for {user_id}. Resetting.")
                await db.reset_partner(user_id)
                partner_id = None

    if not partner_id:
        await message.reply_text("⚠️ You are not connected with a partner. Use /search.")
        return

    try:
        await message.copy(chat_id=partner_id)

        # --- UPDATED: Add a RANDOM reaction to the original message ---
        # We run this in the background so it doesn't slow down the relay.
        async def add_reaction():
            try:
                # A list of positive, simple emojis that work well as reactions
                random_emoji = random.choice(REACTION_EMOJIS) # <-- CHANGE HERE         
                
                await message.react(random_emoji) # <-- USE THE RANDOM EMOJI
            except Exception as e:
                # This can fail if the user has disabled reactions for the bot.
                # We just log it and don't let it crash the bot.
                print(f"[Reaction] Failed to add reaction: {e}")
        
        client.loop.create_task(add_reaction())
        update_activity(user_id)
        update_activity(partner_id)
        print(f"[relay_all] Relayed message {user_id} ➝ {partner_id}")

    except FloodWait as e:
        print(f"[relay_all] FloodWait: {e.value}s. Waiting...")
        await asyncio.sleep(e.value)
        await message.copy(chat_id=partner_id)
        print(f"[relay_all] Relayed message {user_id} ➝ {partner_id} after FloodWait")

    except Exception as e:
        print(f"[relay_all] Relay failed for {user_id}: {e}")
        await client.send_message(user_id, "❌ Message failed. Connection ended. Use /search to find a new partner.")
        sessions.pop(user_id, None)
        await db.update_status(user_id, "idle")

        if partner_id:
            await client.send_message(partner_id, "❌ Connection lost due to an error. Use /search to find a new partner.")
            sessions.pop(partner_id, None)
            await db.reset_partners(user_id, partner_id)
            await db.update_status(partner_id, "idle")
        return

    try:
        client.loop.create_task(log_message(client, user_id, message.from_user.first_name, message))
    except Exception as e:
        print(f"[relay_all] Logging failed: {e}")
