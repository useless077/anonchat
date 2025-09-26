# plugins/start.py
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users import db
from matching import add_user, remove_user, get_partner
from utils import log_message


@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    add_user(user_id)
    await db.add_user(user_id, {"gender": "", "age": None, "location": "", "dp": None})
    
    buttons = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("📝 Update Profile", callback_data="profile"),
            InlineKeyboardButton("🔍 Search Partner", callback_data="search")
        ]]
    )
    
    await message.reply_text(
        "👋 Welcome to Anonymous Chat Bot!\nHappy chatting! 🎉",
        reply_markup=buttons
    )


@Client.on_message(filters.private & filters.command("profile"))
async def handle_profile(client, message):
    user_id = message.from_user.id
    await message.reply_text("📝 Please send your gender, age, and location one by one.")


@Client.on_message(filters.private & filters.command("search"))
async def handle_search(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user or not user.get("profile") or not user["profile"].get("gender"):
        await message.reply_text("⚠️ Please update your profile first with /profile.")
        return
    
    partner_id = get_partner(user_id)
    if partner_id:
        await message.reply_text("✅ Found your partner! Let's start chatting! 🎉")
        await client.send_message(partner_id, "✅ You’ve been connected! Say hi 👋")
    else:
        await message.reply_text("⏳ Waiting for a partner... Please wait.")


# Optional: handle callback buttons
@Client.on_callback_query(filters.regex("profile"))
async def cb_profile(client, callback_query):
    await handle_profile(client, callback_query.message)


@Client.on_callback_query(filters.regex("search"))
async def cb_search(client, callback_query):
    await handle_search(client, callback_query.message)
