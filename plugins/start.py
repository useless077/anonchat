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
@Client.on_message(filters.private & filters.command("search"))
async def search_cmd(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}

    if not profile.get("gender") or not profile.get("age") or not profile.get("location"):
        await message.reply_text("⚠️ Complete profile first with /profile")
        return
    
    if user_id in sessions or user.get("partner_id"):
        await message.reply_text("⚠️ You are already chatting. Use /end")
        return

    async with waiting_lock:
        partner_id = None
        for uid in waiting_users:
            if uid != user_id:
                partner_id = uid
                break
        
        if partner_id:
            waiting_users.discard(partner_id)
            
            # Update DB + sessions
            await db.set_partners_atomic(user_id, partner_id)
            set_partner(user_id, partner_id)

            await db.update_status(user_id, "busy")
            await db.update_status(partner_id, "busy")
            
            # Send partner details
            p1 = (await db.get_user(partner_id)).get("profile", {})
            p2 = profile
            await client.send_message(
                user_id,
                f"✅ Partner found!\n👤 Name: {p1.get('name','')}\n⚧ Gender: {p1.get('gender','')}\n🎂 Age: {p1.get('age','')}\n📍 Location: {p1.get('location','')}"
            )
            await client.send_message(
                partner_id,
                f"✅ Partner found!\n👤 Name: {p2.get('name','')}\n⚧ Gender: {p2.get('gender','')}\n🎂 Age: {p2.get('age','')}\n📍 Location: {p2.get('location','')}"
            )
        else:
            waiting_users.add(user_id)
            await message.reply_text("⏳ Finding your partner... Please wait.")


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
        await search_cmd(client, message)
    else:
        await search_cmd(client, message)


@Client.on_message(filters.private & filters.command("end"))
async def end_chat(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    partner_id = user.get("partner_id")

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

        await client.send_message(user_id, "⚠️ You are not connected to anyone.")


# ----------------- Relay Messages & Media -----------------

@Client.on_message(filters.private & filters.incoming & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def relay_all(client: Client, message: Message):
    user_id = message.from_user.id
    print(f"[relay_all] Message from {user_id}")

    # Skip if user is in profile setup
    if user_id in profile_states:
        print(f"[relay_all] {user_id} still in profile setup, skipping")
        return

    # Find partner (check sessions first, then DB fallback)
    partner_id = sessions.get(user_id)
    if not partner_id:
        user_db = await db.get_user(user_id)
        partner_id = user_db.get("partner_id") if user_db else None
        if partner_id:
            sessions[user_id] = partner_id
            sessions[partner_id] = user_id  # make sure reverse link exists
            print(f"[relay_all] Partner {partner_id} loaded from DB for {user_id}")

    if not partner_id:
        await message.reply_text("⚠️ You are not connected with a partner. Use /search.")
        return

    # Relay message
    try:
        await message.copy(chat_id=partner_id)
        update_activity(user_id)
        update_activity(partner_id)
        print(f"[relay_all] Relayed message {user_id} ➝ {partner_id}")
    except Exception as e:
        print(f"[relay_all] Relay failed: {e}")
        sessions.pop(user_id, None)
        sessions.pop(partner_id, None)
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        await client.send_message(user_id, "❌ Message failed. Partner may have left. Use /end.")
        return

    # Log the message
    try:
        await log_message(client, user_id, message.from_user.first_name, message)
        print(f"[relay_all] Logged message from {user_id}")
    except Exception as e:
        print(f"[relay_all] Logging failed: {e}")
