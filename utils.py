# utils.py
from datetime import datetime
from pyrogram.types import Message
import config
from database.users import Database

# Initialize Database
db = Database(mongo_uri=config.MONGO_URI, db_name=config.MONGO_DB_NAME)

async def log_message(app, sender_id, sender_name, msg: Message):
    """
    Logs a message to the LOG_CHANNEL and optionally saves/updates user in database.
    """
    # Ensure DB connection is alive
    try:
        await db.connect()
    except Exception as e:
        print(f"Database connection error: {e}")

    # Create log text
    text = f"[{datetime.utcnow().isoformat()}Z]\nFrom: <a href='tg://user?id={sender_id}'>{sender_name}</a>"
    
    if msg.text:
        text += f"\nText: {msg.text}"
        await app.send_message(config.LOG_CHANNEL, text, parse_mode="html")
    elif msg.photo:
        await app.send_photo(config.LOG_CHANNEL, msg.photo[-1].file_id)
    elif msg.sticker:
        await app.send_sticker(config.LOG_CHANNEL, msg.sticker.file_id)
    elif msg.animation:
        await app.send_animation(config.LOG_CHANNEL, msg.animation.file_id)
    else:
        await app.send_message(config.LOG_CHANNEL, f"Other type from {sender_name}", parse_mode="html")
    
    # Optional: add or update user in database
    profile = {
        "gender": "unknown",
        "age": 0,
        "location": "unknown",
        "dp": None
    }
    try:
        await db.add_user(sender_id, profile)
    except Exception as e:
        print(f"Failed to add/update user in DB: {e}")
