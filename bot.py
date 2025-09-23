import logging
import sys
from pyrogram import Client, filters
from config import Config
from database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Initialize database
db = Database(Config.MONGO_URI, Config.DB_NAME)

# Initialize Pyrogram bot
bot = Client(
    "anonchat-bot",
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    workers=50,
    sleep_threshold=5,
)

# --- Bot Events --- #

@bot.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    # Add user to DB
    await db.add_user(user_id, {
        "gender": "",
        "age": None,
        "location": "",
        "dp": None
    })
    await message.reply_text("Welcome to Anonymous Chat Bot! Your profile is created.")

@bot.on_message(filters.private & filters.command("profile"))
async def profile(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {})
    text = f"Your Profile:\n\n"
    text += f"Gender: {profile.get('gender', 'N/A')}\n"
    text += f"Age: {profile.get('age', 'N/A')}\n"
    text += f"Location: {profile.get('location', 'N/A')}\n"
    await message.reply_text(text)

# Command to set profile
@bot.on_message(filters.private & filters.command("setprofile"))
async def set_profile(client, message):
    user_id = message.from_user.id
    # Format: /setprofile gender age location
    try:
        _, gender, age, location = message.text.split(maxsplit=3)
        profile = {
            "gender": gender,
            "age": int(age),
            "location": location,
            "dp": message.from_user.photo.file_id if message.from_user.photo else None
        }
        await db.add_user(user_id, profile)
        await message.reply_text("Profile updated successfully!")
    except Exception as e:
        await message.reply_text("Usage: /setprofile gender age location")
        logging.error(f"Error setting profile: {e}")

# --- Startup / Shutdown --- #
async def startup():
    logging.info("Connecting to database...")
    await db.connect()
    logging.info("Database connected.")

async def shutdown():
    logging.info("Closing database...")
    await db.close()
    logging.info("Database closed.")

# --- Run Bot --- #
if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(startup())
    try:
        bot.run()
    finally:
        loop.run_until_complete(shutdown())
