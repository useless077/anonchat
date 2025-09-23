# plugins/start.py
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users import Database
from matching import add_user, remove_user, get_partner
from utils import log_message

db = Database(uri="your-mongo-uri", db_name="your-db-name")  # Replace with config values

async def start(client, message):
    user_id = message.from_user.id
    add_user(user_id)
    await db.add_user(user_id, {"gender": "", "age": None, "location": "", "dp": None})
    
    buttons = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Update Profile", callback_data="profile"),
            InlineKeyboardButton("Search Partner", callback_data="search")
        ]]
    )
    
    await message.reply_text(
        "👋 Welcome to Anonymous Chat Bot!\nHappy chatting! 🎉",
        reply_markup=buttons
    )

async def handle_profile(client, message):
    user_id = message.from_user.id
    # Ask details one by one logic here
    await message.reply_text("Please send your gender, age, location one by one.")

async def handle_search(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user or not user.get("profile"):
        await message.reply_text("⚠️ Update your profile first!")
        return
    partner_id = get_partner(user_id)
    if partner_id:
        await message.reply_text("✅ Found your partner! Let's start chatting!", reply_markup=None)
    else:
        await message.reply_text("⏳ Waiting for a partner...")

# Bind commands
def register_handlers(bot: Client):
    bot.add_handler(filters.private & filters.command("start"), start)
    bot.add_handler(filters.private & filters.command("profile"), handle_profile)
    bot.add_handler(filters.private & filters.command("search"), handle_search)
