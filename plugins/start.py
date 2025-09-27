# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
import config   # for LOG_CHANNEL
from utils import (    # <- this is your combined file
    add_user,
    remove_user,
    get_partner,
    set_partner,
    update_activity,
    start_profile_timer,
    check_idle_chats,
    sessions,
    active_users,
    log_message
)
from database.users import db


# ----------------- In-memory states -----------------
profile_states = {}   # user_id -> step
profile_data = {}     # user_id -> temporary dict
profile_timeouts = {} # user_id -> datetime
active_chats = {}     # user_id -> (partner_id, last_message_time)
waiting_users = set() # users waiting for partner
waiting_lock = asyncio.Lock()  # ensure safe access

# ----------------- Constants -----------------
PROFILE_TIMEOUT = 300   # 5 mins
CHAT_IDLE_TIMEOUT = 900 # 15 mins

# ----------------- Active Users -----------------
active_users = set()   # user_id
sessions = {}          # user_id -> partner_id

# ----------------- Utility Functions -----------------
def add_user(user_id: int):
    active_users.add(user_id)

def remove_user(user_id: int):
    active_users.discard(user_id)
    partner_id = sessions.pop(user_id, None)
    if partner_id:
        sessions.pop(partner_id, None)
        active_chats.pop(partner_id, None)
    active_chats.pop(user_id, None)
    profile_states.pop(user_id, None)
    profile_data.pop(user_id, None)
    profile_timeouts.pop(user_id, None)

def get_partner(user_id: int):
    """Return partner if already exists or None."""
    return sessions.get(user_id)

def set_partner(user1: int, user2: int):
    sessions[user1] = user2
    sessions[user2] = user1
    active_chats[user1] = (user2, datetime.utcnow())
    active_chats[user2] = (user1, datetime.utcnow())

def update_activity(user_id: int):
    active_chats[user_id] = (active_chats[user_id][0], datetime.utcnow()) if user_id in active_chats else None
    partner_id = sessions.get(user_id)
    if partner_id:
        active_chats[partner_id] = (active_chats[partner_id][0], datetime.utcnow())

async def log_message(client, message: Message):
    """Log any message/media to LOG_CHANNEL"""
    try:
        user = message.from_user
        username = user.username or "NoUsername"
        mention = f"[{user.first_name}](tg://user?id={user.id})"
        base_caption = f"📩 Message from {mention}\n🆔 `{user.id}`\n🌐 @{username if user.username else 'NoUsername'}"

        if message.text:
            await client.send_message(LOG_CHANNEL, f"{base_caption}\n\n💬 {message.text}", parse_mode="Markdown")
        else:
            new_caption = base_caption
            if message.caption:
                new_caption += f"\n\n📝 {message.caption}"
            await message.copy(chat_id=LOG_CHANNEL, caption=new_caption)
    except Exception as e:
        print(f"Log error: {e}")

# ----------------- Timeout Monitor -----------------
async def monitor_timeouts(bot: Client):
    while True:
        now = datetime.utcnow()

        # Profile timeout
        for user_id, start_time in list(profile_timeouts.items()):
            if (now - start_time).total_seconds() > PROFILE_TIMEOUT:
                profile_states.pop(user_id, None)
                profile_data.pop(user_id, None)
                profile_timeouts.pop(user_id, None)
                try:
                    await bot.send_message(user_id, "⌛ Profile update expired. Please run /profile again.")
                except: pass

        # Chat idle timeout
        for user_id, (partner_id, last_time) in list(active_chats.items()):
            if (now - last_time).total_seconds() > CHAT_IDLE_TIMEOUT:
                try:
                    await bot.send_message(user_id, "⏳ Chat ended due to inactivity.")
                    await bot.send_message(partner_id, "⏳ Chat ended due to inactivity.")
                except: pass
                remove_user(user_id)
                remove_user(partner_id)

        await asyncio.sleep(10)

async def start_monitoring(bot: Client):
    asyncio.create_task(monitor_timeouts(bot))

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

@Client.on_message(filters.private & filters.command("profile"))
async def profile_cmd(client, message):
    user_id = message.from_user.id
    profile_states[user_id] = "name"
    profile_data[user_id] = {}
    profile_timeouts[user_id] = datetime.utcnow()
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
    if user_id not in profile_states: return
    profile_timeouts[user_id] = datetime.utcnow()
    step = profile_states[user_id]
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
    if user_id in active_chats:
        await message.reply_text("⚠️ You are already chatting. Use /end")
        return

    async with waiting_lock:
        # If someone waiting → connect
        partner_id = None
        for uid in waiting_users:
            if uid != user_id:
                partner_id = uid
                break
        if partner_id:
            waiting_users.discard(partner_id)
            set_partner(user_id, partner_id)
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
    if user_id in active_chats:
        partner_id, _ = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
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
    if user_id in active_chats:
        partner_id, _ = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)
        remove_user(user_id)
        remove_user(partner_id)
        await client.send_message(user_id, "❌ Chat ended.")
        await client.send_message(partner_id, "❌ Chat ended by partner.")
    else:
        await message.reply_text("⚠️ You are not in a chat.")

# ----------------- Relay Messages & Media -----------------
@Client.on_message(filters.private & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def relay_all(client, message: Message):
    user_id = message.from_user.id
    update_activity(user_id)  # refresh last active time

    # Forward to partner if connected
    if user_id in sessions:
        partner_id = sessions[user_id]
        try:
            await message.copy(chat_id=partner_id)
            update_activity(partner_id)
        except Exception as e:
            print(f"Error forwarding to partner: {e}")

    # Forward to LOG_CHANNEL
    try:
        sender_name = message.from_user.first_name
        await log_message(client, user_id, sender_name, message)
    except Exception as e:
        print(f"Error forwarding to LOG_CHANNEL: {e}")
