# utils.py
from datetime import datetime
from pyrogram.types import Message
import config
from database.users import Database

async def log_message(app, sender_id, sender_name, msg: Message):
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
        await app.send_message(
            config.LOG_CHANNEL,
            f"Other type from {sender_name}",
            parse_mode="html"
        )
