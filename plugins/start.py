# plugins/start.py
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users import db
from matching import add_user, remove_user, get_partner, set_partner

profile_states = {}
sessions = {}
active_users = set()
profile_timeout = 5 * 60
chat_idle_timeout = 15 * 60

gender_buttons = InlineKeyboardMarkup([
    [InlineKeyboardButton("♂ Male", callback_data="gender_male"),
     InlineKeyboardButton("♀ Female", callback_data="gender_female"),
     InlineKeyboardButton("⚧ Shemale", callback_data="gender_shemale")]
])

def get_start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Update Profile", callback_data="profile")],
        [InlineKeyboardButton("🔍 Search Partner", callback_data="search")]
    ])

async def timeout_checker(bot: Client):
    while True:
        now = datetime.utcnow()
        for uid, state in list(profile_states.items()):
            if (now - state["last_update"]).total_seconds() > profile_timeout:
                profile_states.pop(uid, None)
                try:
                    await bot.send_message(uid, "⏳ Profile update timed out! Start over using /profile.")
                except:
                    pass
        for uid, partner_id in list(sessions.items()):
            last_msg_time = sessions.get(f"{uid}_last_msg", None)
            if last_msg_time and (now - last_msg_time).total_seconds() > chat_idle_timeout:
                try:
                    await bot.send_message(uid, "❌ Chat ended due to inactivity.")
                    await bot.send_message(partner_id, "❌ Chat ended due to inactivity.")
                except:
                    pass
                sessions.pop(uid, None)
                sessions.pop(partner_id, None)
                sessions.pop(f"{uid}_last_msg", None)
                sessions.pop(f"{partner_id}_last_msg", None)
        await asyncio.sleep(60)

# --- Handlers using decorator style ---
def register_start_handlers(bot: Client):

    @bot.on_message(filters.private & filters.command("start"))
    async def start(client, message):
        user_id = message.from_user.id
        active_users.add(user_id)
        add_user(user_id)
        await db.add_user(user_id, {"gender": "", "age": None, "location": "", "dp": None})

        text = (
            "👋 Welcome to Anonymous Chat Bot!\n🎉 Happy chatting!\n\n"
            "Available commands:\n"
            "👤 /profile - Update your profile\n"
            "🔍 /search - Search a partner\n"
            "❌ /end - End current chat"
        )
        image_url = "https://example.com/cute_hot_girl_ai_generated.jpg"
        await message.reply_photo(image_url, caption=text, reply_markup=get_start_buttons())

    @bot.on_message(filters.private & filters.command("profile"))
    async def profile_start(client, message):
        user_id = message.from_user.id
        profile_states[user_id] = {"step": "name", "data": {}, "last_update": datetime.utcnow()}
        await message.reply_text("📝 Please enter your **Name**:")

    @bot.on_message(filters.private & filters.text)
    async def handle_profile_steps(client, message):
        user_id = message.from_user.id
        if user_id not in profile_states:
            return
        state = profile_states[user_id]
        state["last_update"] = datetime.utcnow()
        step = state["step"]
        text = message.text.strip()

        if step == "name":
            state["data"]["name"] = text
            state["step"] = "gender"
            await message.reply_text("✅ Name added. Select your **Gender**:", reply_markup=gender_buttons)
        elif step == "age":
            if not text.isdigit() or not (10 <= int(text) <= 120):
                await message.reply_text("⚠️ Invalid age! Enter a number 10-120.")
                return
            state["data"]["age"] = int(text)
            state["step"] = "location"
            await message.reply_text("✅ Age added. Now send your **Location**:")
        elif step == "location":
            state["data"]["location"] = text
            await db.add_user(user_id, state["data"])
            profile_states.pop(user_id, None)
            await message.reply_text("🎉 Profile updated successfully! You can now search a partner using /search.")

    @bot.on_callback_query()
    async def gender_callback(client, callback_query):
        user_id = callback_query.from_user.id
        if user_id not in profile_states:
            await callback_query.answer("⚠️ Start profile update first using /profile", show_alert=True)
            return
        gender_map = {"gender_male": "Male", "gender_female": "Female", "gender_shemale": "Shemale"}
        selected_gender = gender_map.get(callback_query.data)
        profile_states[user_id]["data"]["gender"] = selected_gender
        profile_states[user_id]["step"] = "age"
        profile_states[user_id]["last_update"] = datetime.utcnow()
        await callback_query.answer(f"✅ Gender set to {selected_gender}")
        await callback_query.message.reply_text("Now enter your **Age**:")

    @bot.on_message(filters.private & filters.command("search"))
    async def search_partner(client, message):
        user_id = message.from_user.id
        user = await db.get_user(user_id)
        if not user or not user.get("profile") or not user["profile"].get("gender"):
            await message.reply_text("⚠️ Update your profile first using /profile")
            return
        partner_id = get_partner(user_id)
        if partner_id:
            sessions[user_id] = partner_id
            sessions[partner_id] = user_id
            sessions[f"{user_id}_last_msg"] = datetime.utcnow()
            sessions[f"{partner_id}_last_msg"] = datetime.utcnow()
            await message.reply_text("✅ Found your partner! Let's start chatting! 🎉")
            await client.send_message(partner_id, "✅ You are connected to a new partner! 🎉")
        else:
            await message.reply_text("⏳ Waiting for a partner...")

    @bot.on_message(filters.private & filters.command("end"))
    async def end_chat(client, message):
        user_id = message.from_user.id
        partner_id = sessions.pop(user_id, None)
        if partner_id:
            sessions.pop(partner_id, None)
            sessions.pop(f"{user_id}_last_msg", None)
            sessions.pop(f"{partner_id}_last_msg", None)
            await message.reply_text("❌ You ended the chat.")
            await client.send_message(partner_id, "❌ Your partner ended the chat.")

    # Start background task
    asyncio.create_task(timeout_checker(bot))
