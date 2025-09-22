from datetime import datetime
from pyrogram.types import Message
from config import Config
from db import logs

def mention_html(uid, name):
    return f'<a href="tg://user?id={uid}">{name}</a>'

async def log_message(app, sender_id, sender_name, msg: Message):
    text = f"[{datetime.utcnow().isoformat()}Z]\nFrom: {mention_html(sender_id, sender_name)}"
    if msg.text:
        text += f"\nText: {msg.text}"
        await app.send_message(Config.AUDIT_CHAT_ID, text, parse_mode="html")
    elif msg.sticker:
        await app.send_sticker(Config.AUDIT_CHAT_ID, msg.sticker.file_id)
    elif msg.animation:
        await app.send_animation(Config.AUDIT_CHAT_ID, msg.animation.file_id)
    elif msg.photo:
        await app.send_photo(Config.AUDIT_CHAT_ID, msg.photo[-1].file_id)
    else:
        await app.send_message(Config.AUDIT_CHAT_ID, f"Other type from {mention_html(sender_id,sender_name)}", parse_mode="html")

    await logs.insert_one({
        "uid": sender_id,
        "name": sender_name,
        "date": datetime.utcnow(),
        "type": msg.media if msg.media else "text",
        "text": msg.text if msg.text else None
    })
