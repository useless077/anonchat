from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from database.users import db
from matching import add_user, get_partner
import asyncio

# Temporary storage for profile updates
profile_steps = {}  # user_id -> {"step": step_number, "data": {}}

# --- START COMMAND ---
@Client.on_message(filters.private & filters.command("start"))
async def start(client: Client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    await db.add_user(user_id, {"name": "", "gender": "", "age": None, "location": "", "dp": None})

    # Inline buttons for commands
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Update Profile", callback_data="profile")],
            [InlineKeyboardButton("🔍 Search Partner", callback_data="search")]
        ]
    )

    await message.reply_photo(
        photo="https://i.ibb.co/5T6M7vH/cute-girl.jpg",  # AI-generated placeholder image
        caption=(
            "👋 Hello! Welcome to **Anonymous Chat Bot** 🎉\n\n"
            "Available commands:\n"
            "📝 /profile - Update your profile step by step\n"
            "🔍 /search - Search for a partner\n"
            "⚠️ Make sure your profile is complete before searching!"
        ),
        reply_markup=buttons
    )


# --- PROFILE CALLBACK ---
@Client.on_callback_query(filters.regex("profile"))
async def profile_callback(client, callback_query):
    user_id = callback_query.from_user.id
    profile_steps[user_id] = {"step": 1, "data": {}}
    await callback_query.message.edit_text("👤 Please enter your **name**:")


# --- SEARCH CALLBACK ---
@Client.on_callback_query(filters.regex("search"))
async def search_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {})

    if not profile.get("name") or not profile.get("gender") or not profile.get("age") or not profile.get("location"):
        await callback_query.message.edit_text("⚠️ Please complete your profile first!")
        return

    partner_id = get_partner(user_id)
    if partner_id:
        await callback_query.message.edit_text("✅ Found your partner! Let's start chatting! 💬")
    else:
        await callback_query.message.edit_text("⏳ Waiting for a partner...")


# --- PROFILE MESSAGE HANDLER ---
@Client.on_message(filters.private)
async def profile_steps_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id not in profile_steps:
        return  # Ignore messages if user not updating profile

    step_info = profile_steps[user_id]
    step = step_info["step"]
    data = step_info["data"]

    # Step 1: Name
    if step == 1:
        data["name"] = message.text
        step_info["step"] = 2
        await message.reply_text(f"✅ Name set as **{message.text}**.\n\nSelect your **gender**:",
                                 reply_markup=InlineKeyboardMarkup([
                                     [InlineKeyboardButton("Male 👨", callback_data="gender_male"),
                                      InlineKeyboardButton("Female 👩", callback_data="gender_female"),
                                      InlineKeyboardButton("Other 🌈", callback_data="gender_other")]
                                 ]))
        return

    # Step 2: Age
    if step == 3:
        if not message.text.isdigit():
            await message.reply_text("⚠️ Please enter a valid age number:")
            return
        data["age"] = int(message.text)
        step_info["step"] = 4
        await message.reply_text("📍 Now send your **location**:")
        return

    # Step 3: Location
    if step == 4:
        data["location"] = message.text
        await db.add_user(user_id, data)
        await message.reply_text("✅ Profile updated successfully! You can now search for a partner.")
        profile_steps.pop(user_id, None)
        return


# --- GENDER BUTTON HANDLER ---
@Client.on_callback_query(filters.regex(r"gender_(male|female|other)"))
async def gender_button(client, callback_query):
    user_id = callback_query.from_user.id
    gender = callback_query.data.split("_")[1]

    if user_id not in profile_steps:
        await callback_query.answer("⚠️ Please start updating your profile first!", show_alert=True)
        return

    profile_steps[user_id]["data"]["gender"] = gender
    profile_steps[user_id]["step"] = 3
    await callback_query.message.edit_text(f"✅ Gender set as **{gender.capitalize()}**.\n\nNow enter your **age**:")
