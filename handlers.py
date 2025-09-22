from pyrogram import Client, filters
from pyrogram.types import Message
from db import get_user, users
from matching import enqueue, dequeue_pair
from utils import log_message

@Client.on_message(filters.command("start"))
async def start_cmd(client, msg: Message):
    await msg.reply_text("👋 Welcome to Anonymous Chat!\n/setprofile to setup\n/find to connect\n/disconnect to stop\n/shareprofile to reveal")

@Client.on_message(filters.command("setprofile"))
async def setprofile(client, msg: Message):
    parts = msg.text.split(" ", 1)
    if len(parts) < 2:
        return await msg.reply_text("Usage: /setprofile Name|Gender|Age|Location|Language")
    try:
        name, gender, age, loc, lang = [p.strip() for p in parts[1].split("|")]
    except:
        return await msg.reply_text("Invalid format.")
    await users.update_one({"_id": msg.from_user.id}, {"$set": {
        "profile": {"name": name, "gender": gender, "age": int(age), "location": loc, "language": lang}
    }}, upsert=True)
    await msg.reply_text("✅ Profile saved.")

@Client.on_message(filters.command("profile"))
async def profile(client, msg: Message):
    u = await get_user(msg.from_user.id)
    p = u.get("profile", {})
    if not p: return await msg.reply_text("No profile set.")
    await msg.reply_text(f"👤 Profile:\nName: {p.get('name')}\nGender: {p.get('gender')}\nAge: {p.get('age')}\nLocation: {p.get('location')}\nLanguage: {p.get('language')}")

@Client.on_message(filters.command("find"))
async def find(client, msg: Message):
    uid = msg.from_user.id
    await enqueue(uid)
    await msg.reply_text("🔍 Searching for partner...")
    pair = await dequeue_pair()
    if pair:
        a, b = pair
        await client.send_message(a, "🎉 Connected! Say hi.")
        await client.send_message(b, "🎉 Connected! Say hi.")

@Client.on_message(filters.command("disconnect"))
async def disconnect(client, msg: Message):
    u = await get_user(msg.from_user.id)
    partner = u.get("partner_id")
    if partner:
        await users.update_one({"_id": partner}, {"$set":{"status":"idle","partner_id":None}})
        await client.send_message(partner,"⚠️ Partner disconnected.")
    await users.update_one({"_id": u["_id"]}, {"$set":{"status":"idle","partner_id":None}})
    await msg.reply_text("Disconnected.")

@Client.on_message(filters.command("shareprofile"))
async def shareprofile(client, msg: Message):
    u = await get_user(msg.from_user.id)
    partner = u.get("partner_id")
    if not partner: return await msg.reply_text("No partner.")
    p = u.get("profile",{})
    txt = (f"🤝 Partner shared profile:\nName: {p.get('name')}\nGender: {p.get('gender')}\n"
           f"Age: {p.get('age')}\nLocation: {p.get('location')}\nLanguage: {p.get('language')}")
    await client.send_message(partner, txt)
    await msg.reply_text("✅ Shared with partner.")

@Client.on_message(~filters.command(["start","setprofile","profile","find","disconnect","shareprofile"]))
async def relay(client, msg: Message):
    u = await get_user(msg.from_user.id)
    partner = u.get("partner_id")
    await log_message(client, msg.from_user.id, msg.from_user.first_name, msg)
    if not partner:
        return await msg.reply_text("Not connected. Use /find.")
    if msg.text:
        await client.send_message(partner, msg.text)
    elif msg.sticker:
        await client.send_sticker(partner, msg.sticker.file_id)
    elif msg.photo:
        await client.send_photo(partner, msg.photo[-1].file_id)
    elif msg.animation:
        await client.send_animation(partner, msg.animation.file_id)
    elif msg.video:
        await client.send_video(partner, msg.video.file_id)
    elif msg.voice:
        await client.send_voice(partner, msg.voice.file_id)
    else:
        await client.send_message(partner,"Unsupported message type.")
