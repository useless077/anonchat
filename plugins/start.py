# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users import db
from matching import add_user, remove_user, get_partner

# In-memory states
profile_states = {}   # user_id -> step
profile_data = {}     # user_id -> temporary dict
profile_timeouts = {} # user_id -> datetime
active_chats = {}     # user_id -> (partner_id, last_message_time)

PROFILE_TIMEOUT = 300   # 5 mins
CHAT_IDLE_TIMEOUT = 900 # 15 mins


# -------- Background Timeout Monitor --------
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
                    await client.send_message(user_id, "⌛ Profile update expired. Please run /profile again.")
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


async def start_monitoring(bot: Client):
    asyncio.create_task(monitor_timeouts(bot))


# -------- Start Command --------
@Client.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    add_user(user_id)

    # only add empty profile if not exists
    user = await db.get_user(user_id)
    if not user or not user.get("profile"):
        await db.add_user(user_id, {"name": "", "gender": "", "age": None, "location": "", "dp": None})

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Update Profile", callback_data="profile")],
        [InlineKeyboardButton("Search Partner", callback_data="search")]
    ])

    await message.reply_photo(
        photo="https://graph.org/file/1e335a03940be708a9407.jpg",
        caption="👋 Welcome to Anonymous Chat Bot!\n\nUse:\n/profile - Update profile\n/search - Find a partner\n/myprofile - View profile\n/next - Switch partner\n/end - End chat",
        reply_markup=buttons
    )


# -------- Profile Command --------
@Client.on_message(filters.private & filters.command("profile"))
async def profile_cmd(client, message):
    user_id = message.from_user.id
    profile_states[user_id] = "name"
    profile_data[user_id] = {}
    profile_timeouts[user_id] = datetime.utcnow()
    await message.reply_text("✏️ Send your full name:")


# -------- Profile Steps --------
@Client.on_message(filters.private & ~filters.command(["start","profile","search","next","end","myprofile"]))
async def profile_steps(client, message):
    user_id = message.from_user.id
    if user_id not in profile_states:
        return

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
        await message.reply_text("✅ Name saved. Now choose gender:", reply_markup=buttons)

    elif step == "age":
        if not text.isdigit() or not (10 <= int(text) <= 99):
            await message.reply_text("❌ Enter valid age (10-99)")
            return
        profile_data[user_id]["age"] = int(text)
        profile_states[user_id] = "location"
        await message.reply_text("✅ Age saved. Now send your location (city/country):")

    elif step == "location":
        profile_data[user_id]["location"] = text

        # merge with existing profile
        user = await db.get_user(user_id)
        profile = user.get("profile", {}) if user else {}
        profile.update(profile_data[user_id])
        await db.add_user(user_id, profile)

        profile_states.pop(user_id, None)
        profile_data.pop(user_id, None)
        profile_timeouts.pop(user_id, None)
        await message.reply_text("🎉 Profile updated successfully!")


# -------- Gender Selection --------
@Client.on_callback_query(filters.regex("^gender_"))
async def gender_cb(client, query):
    user_id = query.from_user.id
    gender = query.data.split("_")[1]
    profile_data[user_id]["gender"] = gender
    profile_states[user_id] = "age"
    await query.answer(f"✅ Gender '{gender}' selected")
    await query.message.reply_text("Now send your age (10-99):")


# -------- My Profile --------
@Client.on_message(filters.private & filters.command("myprofile"))
async def myprofile_cmd(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}
    if not profile or not profile.get("gender"):
        await message.reply_text("⚠️ You have not set profile yet. Use /profile")
        return

    caption = f"👤 **Your Profile**\n\n"
    caption += f"• Name: {profile.get('name','')}\n"
    caption += f"• Gender: {profile.get('gender','')}\n"
    caption += f"• Age: {profile.get('age','')}\n"
    caption += f"• Location: {profile.get('location','')}\n"

    await message.reply_text(caption)


# -------- Search Partner --------
@Client.on_message(filters.private & filters.command("search"))
async def search_cmd(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}

    if not profile.get("gender") or not profile.get("age") or not profile.get("location"):
        await message.reply_text("⚠️ Please complete your profile first with /profile")
        return

    partner_id = get_partner(user_id)
    if partner_id:
        active_chats[user_id] = (partner_id, datetime.utcnow())
        active_chats[partner_id] = (user_id, datetime.utcnow())
        await message.reply_text("✅ Partner found! Start chatting!")
        await client.send_message(partner_id, "✅ You are now connected to a new partner!")
    else:
        await message.reply_text("⏳ Waiting for a partner...")


# -------- Next Partner --------
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


# -------- End Chat --------
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
