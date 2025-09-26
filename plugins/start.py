# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users import db
from matching import add_user, remove_user, get_partner
from utils import log_message

# In-memory state
profile_states = {}      # user_id -> step
profile_data = {}        # user_id -> profile dict
profile_timeouts = {}    # user_id -> datetime
active_chats = {}        # user_id -> (partner_id, last_message_time)

PROFILE_TIMEOUT = 300    # 5 min
CHAT_IDLE_TIMEOUT = 900  # 15 min

# ---------------- Timeout monitor ---------------- #
async def monitor_timeouts(client: Client):
    while True:
        now = datetime.utcnow()

        # Profile timeout
        for user_id, start_time in list(profile_timeouts.items()):
            if (now - start_time).total_seconds() > PROFILE_TIMEOUT:
                profile_states.pop(user_id, None)
                profile_data.pop(user_id, None)
                profile_timeouts.pop(user_id, None)
                try:
                    await client.send_message(user_id, "⌛ Profile update time expired. Please start again.")
                except:
                    pass

        # Chat idle timeout
        for user_id, (partner_id, last_time) in list(active_chats.items()):
            if (now - last_time).total_seconds() > CHAT_IDLE_TIMEOUT:
                try:
                    await client.send_message(user_id, "⏳ Chat ended due to inactivity.")
                    await client.send_message(partner_id, "⏳ Chat ended due to inactivity.")
                except:
                    pass
                remove_user(user_id)
                remove_user(partner_id)
                active_chats.pop(user_id, None)
                active_chats.pop(partner_id, None)

        await asyncio.sleep(10)

async def start_monitor(client: Client):
    asyncio.create_task(monitor_timeouts(client))

# ---------------- Commands ---------------- #
@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    add_user(user_id)
    await db.add_user(user_id, {"gender": "", "age": None, "location": "", "dp": None})

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Update Profile", callback_data="profile")],
        [InlineKeyboardButton("Search Partner", callback_data="search")]
    ])

    await message.reply_photo(
        photo="https://graph.org/file/1e335a03940be708a9407.jpg",
        caption=(
            "👋 Welcome to Anonymous Chat Bot!\n\n"
            "🎉 Happy chatting!\n\n"
            "Available commands:\n"
            "/profile - Update your profile\n"
            "/search - Find a partner\n"
            "/next - Switch partner\n"
            "/end - End chat"
        ),
        reply_markup=buttons
    )

@Client.on_message(filters.private & filters.command("profile"))
async def update_profile(client, message):
    user_id = message.from_user.id
    profile_states[user_id] = "name"
    profile_data[user_id] = {}
    profile_timeouts[user_id] = datetime.utcnow()
    await message.reply_text("✍️ Please send your **full name**:")

@Client.on_message(filters.private & filters.command("search"))
async def search_partner(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user or not user.get("gender"):
        await message.reply_text("⚠️ Please update your profile first using /profile")
        return

    partner_id = get_partner(user_id)
    if partner_id:
        active_chats[user_id] = (partner_id, datetime.utcnow())
        active_chats[partner_id] = (user_id, datetime.utcnow())
        await message.reply_text("✅ Partner found! Start chatting!")
        await client.send_message(partner_id, "✅ You are now connected to a new partner!")
    else:
        await message.reply_text("⏳ Waiting for a partner...")

@Client.on_message(filters.private & filters.command("next"))
async def next_partner(client, message):
    user_id = message.from_user.id
    if user_id in active_chats:
        partner_id, _ = active_chats.pop(user_id)
        if partner_id in active_chats:
            active_chats.pop(partner_id, None)
        remove_user(user_id)
        remove_user(partner_id)
        await client.send_message(user_id, "🔄 Searching for a new partner...")
        await client.send_message(partner_id, "⚠️ Your partner left the chat.")
        await search_partner(client, message)
    else:
        await search_partner(client, message)

@Client.on_message(filters.private & filters.command("end"))
async def end_chat(client, message):
    user_id = message.from_user.id
    if user_id in active_chats:
        partner_id, _ = active_chats.pop(user_id)
        if partner_id in active_chats:
            active_chats.pop(partner_id, None)
        remove_user(user_id)
        remove_user(partner_id)
        await client.send_message(user_id, "❌ Chat ended.")
        await client.send_message(partner_id, "❌ Chat ended by partner.")
    else:
        await message.reply_text("⚠️ You are not in a chat currently.")

# ---------------- Profile step handling ---------------- #
@Client.on_message(filters.private & ~filters.command(["start", "profile", "search", "next", "end"]))
async def profile_steps(client, message):
    user_id = message.from_user.id
    if user_id not in profile_states:
        return

    profile_timeouts[user_id] = datetime.utcnow()
    step = profile_states[user_id]
    text = (message.text or "").strip()

    if step == "name":
        profile_data[user_id]["name"] = text
        profile_states[user_id] = "gender"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Male", callback_data="gender_male")],
            [InlineKeyboardButton("Female", callback_data="gender_female")],
            [InlineKeyboardButton("Shemale", callback_data="gender_shemale")]
        ])
        await message.reply_text("✅ Name added! Now select your gender:", reply_markup=buttons)

    elif step == "age":
        if not text.isdigit() or not (10 <= int(text) <= 99):
            await message.reply_text("❌ Enter a valid age between 10-99")
            return
        profile_data[user_id]["age"] = int(text)
        profile_states[user_id] = "location"
        await message.reply_text("✅ Age added! Now send your location (city/country):")

    elif step == "location":
        profile_data[user_id]["location"] = text
        await db.add_user(user_id, profile_data[user_id])
        profile_states.pop(user_id, None)
        profile_data.pop(user_id, None)
        profile_timeouts.pop(user_id, None)
        await message.reply_text("🎉 Profile updated successfully!")

# ---------------- Gender callback ---------------- #
@Client.on_callback_query()
async def gender_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if callback_query.data.startswith("gender_"):
        gender = callback_query.data.split("_")[1]
        profile_data[user_id]["gender"] = gender
        profile_states[user_id] = "age"
        await callback_query.answer(f"✅ Gender '{gender}' selected!")
        await callback_query.message.reply_text("Great! Now send your age (10-99)")
    elif callback_query.data == "profile":
        await update_profile(client, callback_query.message)
    elif callback_query.data == "search":
        await search_partner(client, callback_query.message)
