# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters
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

# ----------------- Commands -----------------
@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    add_user(user_id)

    user = await db.get_user(user_id)
    if not user or not user.get("profile"):
        await db.add_user(user_id, {"name": "", "gender": "", "age": None, "location": "", "dp": None})

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Update Profile", callback_data="profile")],
        [InlineKeyboardButton("Search Partner", callback_data="search")]
    ])
    await message.reply_photo(
        photo="https://graph.org/file/1e335a03940be708a9407.jpg",
        caption="👋 Welcome!\nCommands:\n/profile\n/search\n/myprofile\n/next\n/end",
        reply_markup=buttons
    )

# ----------------- Callback Handlers -----------------
@Client.on_callback_query(filters.regex("^search$"))
async def search_cb(client, query):
    """Handles the 'Search Partner' button click."""
    # We create a fake message object to reuse the search_command logic
    # This is a clean way to avoid duplicating code.
    await query.answer() # Acknowledge the button click
    message = Message._from_client(
        client,
        {
            "message_id": query.message.message_id,
            "from": query.from_user,
            "date": query.message.date,
            "chat": query.message.chat
        }
    )
    # Now call the main search command function
    await search_command(client, message)

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

    # Use the timer from utils.py
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

@Client.on_message(filters.private & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def profile_steps(client, message):
    user_id = message.from_user.id
    
    # If not in profile setup, let relay_all handle
    if user_id not in profile_states: 
        return
        
    profile_timeouts[user_id] = datetime.utcnow()
    step = profile_states[user_id]
    
    # Block media during profile setup
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
        
        # Clear states
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
    caption = f"👤 **Your Profile**\n\n"
    caption += f"• Name: {profile.get('name','')}\n• Gender: {profile.get('gender','')}\n"
    caption += f"• Age: {profile.get('age','')}\n• Location: {profile.get('location','')}\n"
    await message.reply_text(caption)

# ----------------- Search Partner -----------------

@Client.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    user_id = message.from_user.id

    # Check if user is already in a chat or waiting
    if user_id in sessions:
        await message.reply_text("You are already in a chat. Use /end to leave first.")
        return
    if user_id in waiting_users:
        await message.reply_text("You are already searching for a partner... Please wait.")
        return

    # --- THE FIX: Use the lock to prevent race conditions ---
    async with waiting_lock:
        # We must re-check the waiting list inside the lock
        if user_id in waiting_users:
             await message.reply_text("You are already searching for a partner... Please wait.")
             return

        # Add user to waiting list
        waiting_users.add(user_id)
        await message.reply_text("🔍 Searching for a partner...")

        # Try to find a partner
        if len(waiting_users) > 1:
            # Get two users from the waiting list
            user1_id = waiting_users.pop()
            user2_id = waiting_users.pop()

            # --- CRITICAL PART ---
            # This is now safe from race conditions
            try:
                # 1. Pair them in the in-memory session
                set_partner(user1_id, user2_id)

                # 2. Pair them in the database ATOMICALLY (with retry logic)
                await db.set_partners_atomic(user1_id, user2_id)

                # 3. Update their status in the database
                await db.update_status(user1_id, "chatting")
                await db.update_status(user2_id, "chatting")

                # 4. Notify both users that they are connected
                await client.send_message(user1_id, "✅ Partner found! Say hi 👋")
                await client.send_message(user2_id, "✅ Partner found! Say hi 👋")

                print(f"[SEARCH] Successfully paired {user1_id} with {user2_id}")

                # Optional: Log the new pairing
                await client.send_message(
                    config.LOG_CHANNEL,
                    f"🤝 New Pairing: <a href='tg://user?id={user1_id}'>User {user1_id}</a> with <a href='tg://user?id={user2_id}'>User {user2_id}</a>",
                    parse_mode="html"
                )
            except Exception as e:
                # If pairing fails for any reason, put users back in waiting list or notify them
                print(f"[SEARCH] Error during pairing {user1_id} and {user2_id}: {e}")
                await client.send_message(user1_id, "❌ An error occurred. Please try searching again.")
                await client.send_message(user2_id, "❌ An error occurred. Please try searching again.")


# ----------------- Next / End -----------------
@Client.on_message(filters.private & filters.command("next"))
async def next_cmd(client, message):
    user_id = message.from_user.id
    partner_id = sessions.pop(user_id, None)

    if partner_id:
        sessions.pop(partner_id, None)

        # Reset both partners in DB
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")

        # Make sure both removed from waiting list
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)

        # Remove from memory sessions
        remove_user(user_id)
        remove_user(partner_id)

        # Notify both users
        await client.send_message(user_id, "🔄 Searching for next partner...")
        await client.send_message(partner_id, "❌ Your partner left.")

        # Start new search immediately for the one who clicked /next
        await search_command(client, message)
    else:
        await search_command(client, message)


@Client.on_message(filters.private & filters.command("end"))
async def end_chat(client, message):
    user_id = message.from_user.id
    
    # --- FIX 2: Check sessions first for consistency ---
    partner_id = sessions.get(user_id)
    if not partner_id:
        # Fallback to DB if not in session
        user = await db.get_user(user_id)
        partner_id = user.get("partner_id") if user else None

    if partner_id:
        # Reset DB
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")

        # Clear sessions + waiting list
        sessions.pop(user_id, None)
        sessions.pop(partner_id, None)
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)

        # Notify both
        await client.send_message(user_id, "❌ You disconnected from the chat.")
        await client.send_message(partner_id, "❌ Your partner disconnected.")
    else:
        # Make sure user is not left in waiting queue
        waiting_users.discard(user_id)
        sessions.pop(user_id, None)
        await db.update_status(user_id, "idle")

        await message.reply_text("⚠️ You are not connected to anyone.")


# ----------------- Relay Messages & Media -----------------

@Client.on_message(filters.private & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def relay_all(client: Client, message: Message):
    user_id = message.from_user.id

    # --- FIX 3: Explicitly check if user is in profile setup ---
    if user_id in profile_states:
        print(f"[relay_all] {user_id} is in profile setup, ignoring message.")
        return

    print(f"[relay_all] Message from {user_id}")

    # --- 1. Find Partner ---
    # Check the in-memory session first for speed
    partner_id = sessions.get(user_id)

    if not partner_id:
        # Fallback to the database if session is empty (e.g., after a restart)
        print(f"[relay_all] Partner not in session for {user_id}, checking DB...")
        user_db = await db.get_user(user_id)
        partner_id = user_db.get("partner_id") if user_db else None

        if partner_id:
            # Restore session if a valid partner is found in the DB
            partner_user = await db.get_user(partner_id)
            if partner_user and partner_user.get("partner_id") == user_id:
                sessions[user_id] = partner_id
                sessions[partner_id] = user_id
                print(f"[relay_all] Partner {partner_id} restored from DB for {user_id}")
            else:
                # Partner in DB is invalid, reset it
                print(f"[relay_all] Invalid partner {partner_id} found in DB for {user_id}. Resetting.")
                await db.reset_partner(user_id)
                partner_id = None

    if not partner_id:
        await message.reply_text("⚠️ You are not connected with a partner. Use /search.")
        return

    # --- 2. Relay Message with Robust Error Handling ---
    try:
        # Use message.copy() for ALL message types for consistency.
        # It handles text, media, captions, etc., perfectly.
        await message.copy(chat_id=partner_id)

        # --- NEW: Add a reaction to the original message ---
        # We run this in the background so it doesn't slow down the relay.
        async def add_reaction():
            try:
                # You can change "👍" to any other emoji like "✅", "❤️", etc.
                await message.react("👍") 
            except Exception as e:
                # This can fail if the user has disabled reactions for the bot.
                # We just log it and don't let it crash the bot.
                print(f"[Reaction] Failed to add reaction: {e}")
        
        client.loop.create_task(add_reaction())

        # Update activity for both users
        update_activity(user_id)
        update_activity(partner_id)
        print(f"[relay_all] Relayed message {user_id} ➝ {partner_id}")

    except FloodWait as e:
        # Handle Telegram rate limits gracefully
        print(f"[relay_all] FloodWait: {e.value}s. Waiting...")
        await asyncio.sleep(e.value)
        # Retry sending the message after waiting
        await message.copy(chat_id=partner_id)
        print(f"[relay_all] Relayed message {user_id} ➝ {partner_id} after FloodWait")

    except Exception as e:
        # Handle other errors (e.g., user blocked the bot, partner deleted chat)
        print(f"[relay_all] Relay failed for {user_id}: {e}")
        
        # Notify the user who sent the message
        await client.send_message(user_id, "❌ Message failed. Connection ended. Use /search to find a new partner.")

        # Safely disconnect both users
        sessions.pop(user_id, None)
        await db.update_status(user_id, "idle")

        if partner_id:
            # Notify the partner that the connection is lost
            await client.send_message(partner_id, "❌ Connection lost due to an error. Use /search to find a new partner.")
            sessions.pop(partner_id, None)
            await db.reset_partners(user_id, partner_id)
            await db.update_status(partner_id, "idle")
        return

    # --- 3. Log the Message (Non-Blocking) ---
    # Use create_task to run logging in the background so it doesn't slow down the relay
    try:
        client.loop.create_task(log_message(client, user_id, message.from_user.first_name, message))
    except Exception as e:
        print(f"[relay_all] Logging failed: {e}")
