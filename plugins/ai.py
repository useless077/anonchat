# plugins/ai.py

import asyncio
import random
import google.generativeai as genai
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import GEMINI_API_KEY, ADMIN_IDS
from database.users import db  # <-- CHANGE THIS LINE

# --- AI INITIALIZATION ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("[AI] Gemini AI Initialized successfully!")
except Exception as e:
    print(f"[AI] Error initializing Gemini AI: {e}")
    model = None

# --- COMMAND HANDLER (/ai on | /ai off) ---
@Client.on_message(filters.command("ai") & filters.group)
async def ai_toggle(client: Client, message: Message):
    chat_id = message.chat.id
    sender = message.from_user

    is_owner = sender.id == ADMIN_IDS
    is_admin = await client.get_chat_member(chat_id, sender.id)
    
    if not (is_owner or is_admin.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)):
        await message.reply("❌ Only group admins or the bot owner can use this command.")
        return

    if len(message.command) < 2:
        await message.reply("Usage: `/ai on` or `/ai off`")
        return

    status = message.command[1].lower()

    if status == "on":
        await db.set_ai_status(chat_id, True) # <-- CHANGE THIS LINE
        await message.reply("✅ **AI Chatbot is now ON** in this group.\nI will reply to messages now!")
    elif status == "off":
        await db.set_ai_status(chat_id, False) # <-- CHANGE THIS LINE
        await message.reply("🛑 **AI Chatbot is now OFF** in this group.")
    else:
        await message.reply("Invalid argument. Use `/ai on` or `/ai off`.")


# --- MAIN AI MESSAGE HANDLER ---
@Client.on_message(filters.group & ~filters.command(["ai", "start", "search", "next", "end", "myprofile", "profile"]))
async def ai_responder(client: Client, message: Message):
    if not model:
        return

    if not await db.get_ai_status(message.chat.id): # <-- CHANGE THIS LINE
        return

    if message.from_user.is_bot:
        return

    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)

    try:
        prompt_text = "You are a friendly and helpful assistant in a Telegram group. Respond to the following message naturally and concisely."

        if message.text:
            prompt = f"{prompt_text}\n\nUser Message: {message.text}"
        elif message.photo:
            prompt = f"{prompt_text}\n\nUser sent a photo with caption: '{message.caption or ''}'. Respond to the image or caption."
        elif message.animation:
            prompt = f"{prompt_text}\n\nUser sent a GIF. Respond to it as if you saw it."
        elif message.sticker:
            prompt = f"{prompt_text}\n\nUser sent a sticker. Respond to it as if you saw it."
        elif message.video:
             prompt = f"{prompt_text}\n\nUser sent a video with caption: '{message.caption or ''}'. Respond to the video or caption."
        else:
            return

        response = model.generate_content(prompt)
        ai_reply = response.text

        await message.reply(ai_reply)

    except Exception as e:
        print(f"[AI] Error generating response: {e}")
