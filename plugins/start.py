from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from bot import bot
from database import Database
from matching import add_user, remove_user, get_partner, set_partner

db = Database()
sessions = {}      # user_id -> partner_id
user_steps = {}    # track profile update steps

# --- Helper Functions --- #
def profile_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Update Profile 📝", callback_data="update_profile")],
        [InlineKeyboardButton("Search Partner 🔍", callback_data="search_partner")]
    ])

def chat_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("End Chat ❌", callback_data="end_chat")]
    ])

async def ask_next_detail(user_id, message: Message):
    step = user_steps[user_id]["step"]
    prompts = ["Gender (Male/Female/Other):", "Age:", "Location:"]
    if step < len(prompts):
        await message.reply_text(prompts[step])
    else:
        # Profile completed
        profile = user_steps[user_id]["profile"]
        await db.add_user(user_id, profile)
        await message.reply_text("✅ Profile updated successfully!", reply_markup=profile_keyboard())
        user_steps.pop(user_id)

# --- Commands --- #
@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    await db.add_user(user_id, {"gender": "", "age": None, "location": "", "dp": None})
    await message.reply_text(
        "👋 Welcome to AnonChat!\nStart chatting anonymously 😎",
        reply_markup=profile_keyboard()
    )

@bot.on_message(filters.private & filters.command("profile"))
async def profile_cmd(client, message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {})
    text = f"Your Profile:\n\nGender: {profile.get('gender', 'N/A')}\nAge: {profile.get('age', 'N/A')}\nLocation: {profile.get('location', 'N/A')}"
    await message.reply_text(text, reply_markup=profile_keyboard())

@bot.on_message(filters.private & filters.command("search"))
async def search_cmd(client, message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user.get("profile") or not user["profile"].get("gender"):
        await message.reply_text("❌ Please update your profile first!", reply_markup=profile_keyboard())
        return

    partner_id = get_partner(user_id)
    if partner_id:
        sessions[user_id] = partner_id
        sessions[partner_id] = user_id
        await message.reply_text(
            "🎉 Partner found! Start chatting now 😎",
            reply_markup=chat_keyboard()
        )
        await client.send_message(partner_id, "🎉 Partner found! Start chatting now 😎", reply_markup=chat_keyboard())
    else:
        await message.reply_text("⏳ Waiting for a partner...", reply_markup=profile_keyboard())

# --- Profile Update Messages --- #
@bot.on_message(filters.private & ~filters.command(["start","profile","search"]))
async def profile_update_msg(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_steps:
        # Start profile update
        user_steps[user_id] = {"step": 0, "profile": {}}

    step = user_steps[user_id]["step"]
    if step == 0:
        user_steps[user_id]["profile"]["gender"] = message.text
    elif step == 1:
        try:
            user_steps[user_id]["profile"]["age"] = int(message.text)
        except ValueError:
            await message.reply_text("❌ Age must be a number. Try again:")
            return
    elif step == 2:
        user_steps[user_id]["profile"]["location"] = message.text

    user_steps[user_id]["step"] += 1
    await ask_next_detail(user_id, message)

# --- Chatting --- #
@bot.on_message(filters.private & ~filters.command(["start","profile","search"]))
async def forward_message(client, message: Message):
    user_id = message.from_user.id
    if user_id in sessions:
        partner_id = sessions[user_id]
        await client.send_message(partner_id, message.text)
    else:
        await message.reply_text("⏳ You are not connected to a partner. Use Search Partner 🔍 to find one.", reply_markup=profile_keyboard())

# --- Callback Query Handlers --- #
@bot.on_callback_query(filters.regex("update_profile"))
async def cb_update_profile(client, callback_query):
    user_id = callback_query.from_user.id
    user_steps[user_id] = {"step": 0, "profile": {}}
    await callback_query.message.reply_text("Let's update your profile.\nGender (Male/Female/Other):")

@bot.on_callback_query(filters.regex("search_partner"))
async def cb_search_partner(client, callback_query):
    user_id = callback_query.from_user.id
    await search_cmd(client, callback_query.message)

@bot.on_callback_query(filters.regex("end_chat"))
async def cb_end_chat(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id in sessions:
        partner_id = sessions.pop(user_id)
        sessions.pop(partner_id, None)
        await callback_query.message.reply_text("❌ Chat ended.", reply_markup=profile_keyboard())
        await client.send_message(partner_id, "❌ Your partner ended the chat.", reply_markup=profile_keyboard())
    else:
        await callback_query.message.reply_text("⚠️ No active chat.", reply_markup=profile_keyboard())
