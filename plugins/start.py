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
    
    # 💡 Logic: User profile setup-ல இல்லைனா, return செய்து message-ஐ அடுத்த handler-க்கு (relay_all) அனுப்ப வேண்டும்.
    if user_id not in profile_states: 
        return
        
    # Profile setup-ல் இருந்தால் மட்டுமே process ஆகும்
    profile_timeouts[user_id] = datetime.utcnow()
    step = profile_states[user_id]
    
    # Profile setup-ன் போது media message வந்தால் reject செய்ய வேண்டும்
    if not message.text and step in ["name", "age", "location"]:
        await message.reply_text("❌ Please send only **text** input for your profile details (Name, Age, Location).")
        return

    text = message.text.strip()
    
    # --- Profile Setup Steps ---
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
        
        # Profile முடிந்தவுடன் state-களை clear செய்ய வேண்டும்
        profile_states.pop(user_id, None)
        profile_data.pop(user_id, None)
        profile_timeouts.pop(user_id, None)
        
        await message.reply_text("🎉 Profile updated successfully!")
    
    # Message-ஐ profile setup process செய்த பிறகு, relay_all-க்கு அனுப்பக் கூடாது.
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
    if user_id in sessions:
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
            set_partner(user_id, partner_id)  # updates sessions both sides
            # Send partner details
            p1 = (await db.get_user(partner_id)).get("profile", {})
            p2 = profile
            await client.send_message(user_id, f"✅ Partner found!\n👤 Name: {p1.get('name','')}\n⚧ Gender: {p1.get('gender','')}\n🎂 Age: {p1.get('age','')}\n📍 Location: {p1.get('location','')}")
            await client.send_message(partner_id, f"✅ Partner found!\n👤 Name: {p2.get('name','')}\n⚧ Gender: {p2.get('gender','')}\n🎂 Age: {p2.get('age','')}\n📍 Location: {p2.get('location','')}")
        else:
            waiting_users.add(user_id)
            await message.reply_text("⏳ Finding your partner... Please wait.")

# ----------------- Next / End -----------------
@Client.on_message(filters.private & filters.command("next"))
async def next_cmd(client, message):
    user_id = message.from_user.id
    if user_id in sessions:
        partner_id = sessions.pop(user_id, None)
        if partner_id:
            sessions.pop(partner_id, None)
            remove_user(user_id)
            remove_user(partner_id)
            await client.send_message(user_id, "🔄 Searching for next partner...")
            await client.send_message(partner_id, "❌ Your partner left.")
            await search_cmd(client, message)
    else:
        await search_cmd(client, message)

@Client.on_message(filters.private & filters.command("end"))
async def end_cmd(client, message):
    user_id = message.from_user.id
    if user_id in sessions:
        partner_id = sessions.pop(user_id, None)
        if partner_id:
            sessions.pop(partner_id, None)
            remove_user(user_id)
            remove_user(partner_id)
            await client.send_message(user_id, "❌ Chat ended.")
            await client.send_message(partner_id, "❌ Chat ended by partner.")
    else:
        await message.reply_text("⚠️ You are not in a chat.")

# ----------------- Relay Messages & Media -----------------
@Client.on_message(filters.private & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def relay_all(client: Client, message: Message):
    user_id = message.from_user.id

    # 🛑 Crucial Check: If the user is in profile setup, STOP the message here.
    if user_id in profile_states:
        return

    # ------------------ 1. Partner Connection Check & Relay ------------------
    partner_id = sessions.get(user_id)
    
    if partner_id:
        update_activity(user_id) # Sender activity update
        
        try:
            # ✅ FIX: message.copy() handles all types (Text, Photo, Video, Sticker, etc.)
            await message.copy(chat_id=partner_id)
            update_activity(partner_id) # Partner activity update
        except Exception as e:
            # Error handling if the partner blocked the bot
            print(f"Error sending to partner: {e}")
            # If relay fails, end the chat and notify the user
            sessions.pop(user_id, None)
            sessions.pop(partner_id, None)
            await client.send_message(user_id, "❌ Your message could not be delivered. Your partner might have blocked the bot or left. Use /end.")

    else:
        # User not connected with a partner
        await message.reply_text("⚠️ You are not connected with a partner. Use /search to find one.")

    # ------------------ 2. Logging (Log Channel-க்கு media/message அனுப்புதல்) ------------------
    # NOTE: The logging logic is correct for sending media to the log channel.
    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else "NoUsername"
        mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
        base_caption = f"📩 Message from {mention}\n🆔 <code>{user.id}</code>\n🌐 {username}"

        # Logging all types of messages to the LOG_CHANNEL
        if message.text:
            await client.send_message(config.LOG_CHANNEL, f"{base_caption}\n\n💬 {message.text}", parse_mode="html")
        elif message.photo:
            await client.send_photo(config.LOG_CHANNEL, message.photo.file_id, caption=base_caption, parse_mode="html")
        elif message.video:
            await client.send_video(config.LOG_CHANNEL, message.video.file_id, caption=base_caption, parse_mode="html")
        elif message.sticker:
            await client.send_sticker(config.LOG_CHANNEL, message.sticker.file_id)
            await client.send_message(config.LOG_CHANNEL, f"{base_caption}\n\n🎭 Sticker", parse_mode="html")
        elif message.animation:
            await client.send_animation(config.LOG_CHANNEL, message.animation.file_id, caption=base_caption, parse_mode="html")
        else:
            await client.send_message(config.LOG_CHANNEL, f"{base_caption}\n\n📎 Other message type", parse_mode="html")
    except Exception as e:
        print(f"Error forwarding to LOG_CHANNEL: {e}")
