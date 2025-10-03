# plugins/ai.py

import asyncio
import random
import re
import google.generativeai as genai
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import GEMINI_API_KEY, ADMIN_IDS
from database.users import db 

# --- AI INITIALIZATION ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("[AI] Gemini AI successful-a initialize aagiduchu!")
except Exception as e:
    print(f"[AI] Gemini AI initialize pannumbothu error: {e}")
    model = None

# --- GLOBAL CACHE AND STATE MANAGEMENT ---
# Cache to store unique Sticker/GIF file IDs sent by users
sticker_cache = set()
gif_cache = set()

# ✅ NEW STATE TRACKER ADDED:
# Cache to track how many consecutive stickers/gifs the bot has sent per chat
# Logic: If user sends media, bot replies with media up to 3 times (as per our last discussion).
# Format: {chat_id: count}
consecutive_media_count = {} 

# --- AI KU PESUM STYLE (PERSONA PROMPT) ---
AI_PERSONA_PROMPT = (
    "You are a friendly, witty, and highly conversational Telegram group member "
    "named 'Gemini'. Your goal is to engage in natural, human-like chat, "
    "keeping conversations flowing and responding to group dynamic. "
    "Do not act like a formal assistant. Keep your replies concise, witty, and relatable. "
    "IMPORTANT: You must always reply in Tanglish, which is a mix of Tamil and English. "
    "Your responses should feel natural to a Tamil-speaking audience."
)

# --- URL/LINK CHECKER PATTERN ---
URL_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+)'

# --- 1. MEDIA CACHE HANDLER (IMPORTANT!) ---
@Client.on_message(filters.group & (filters.sticker | filters.animation))
async def cache_media(client: Client, message: Message):
    if message.from_user and message.from_user.is_bot:
        return
        
    if message.sticker:
        sticker_cache.add(message.sticker.file_id)
    elif message.animation:
        gif_cache.add(message.animation.file_id)


# --- COMMAND HANDLER (/ai on | /ai off) ---
@Client.on_message(filters.command("ai") & filters.group)
async def ai_toggle(client: Client, message: Message):
    chat_id = message.chat.id
    sender = message.from_user

    try:
        is_admin = await client.get_chat_member(chat_id, sender.id)
    except Exception:
        is_admin = None
        
    is_owner = sender.id in ADMIN_IDS if isinstance(ADMIN_IDS, (list, tuple, set)) else sender.id == ADMIN_IDS
    
    if not (is_owner or (is_admin and is_admin.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER))):
        await message.reply("❌ Iva group admin-ya ya bot owner-a than use panna mudiyum.")
        return

    if len(message.command) < 2:
        await message.reply("Usage: `/ai on` ya `/ai off`")
        return

    status = message.command[1].lower()

    if status == "on":
        await db.set_ai_status(chat_id, True)
        await message.reply("✅ **AI Chatbot ipo ON** aagiduchu.\nNaanum conversation la join pannuren!")
    elif status == "off":
        await db.set_ai_status(chat_id, False)
        await message.reply("🛑 **AI Chatbot ipo OFF** aagiduchu.")
    else:
        await message.reply("Correct ah use pannunga. `/ai on` ya `/ai off`.")


# --- MAIN AI MESSAGE HANDLER ---
@Client.on_message(filters.group & ~filters.command(["ai", "start", "search", "next", "end", "myprofile", "profile"]))
async def ai_responder(client: Client, message: Message):
    if not model:
        return

    chat_id = message.chat.id
    if not await db.get_ai_status(chat_id):
        return

    if message.from_user and message.from_user.is_bot:
        return
        
    if message.text and message.text.startswith('/'):
        return

    # --- UPDATED: 100% REPLY LOGIC ---
    # Check if the message is a reply to the bot itself
    is_reply_to_bot = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    )

    # If it's a direct reply, skip the 50% chance check
    if not is_reply_to_bot:
        # If it's not a direct reply, then apply the 50% chance
        is_direct_interaction = bool(
            message.text and (f"@{client.username}" in message.text or client.username in message.text)
        )

        if not is_direct_interaction:
            if random.random() < 0.50: 
                return # Skip responding to keep it human-like

    # --- 3. STATE-BASED REPLY LOGIC ---
    
    # CASE 1: User sent a Sticker or GIF
    if message.sticker or message.animation:
        if message.sticker and sticker_cache:
            # Reply with a random sticker from cache
            media_id = random.choice(list(sticker_cache))
            await client.send_sticker(chat_id, media_id, reply_to_message_id=message.id)
            return
        elif message.animation and gif_cache:
            # Reply with a random GIF from cache
            media_id = random.choice(list(gif_cache))
            await client.send_animation(chat_id, media_id, reply_to_message_id=message.id)
            return
        # If no media in cache, do nothing.
        return

    # CASE 2: User sent Text or other media (Photo, Video)
    # Proceed with text-based logic
    
    # --- LINK/URL CHECK ---
    has_spam_link = False
    if message.entities:
        for entity in message.entities:
            if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                has_spam_link = True
                break
                
    if message.text and re.search(URL_PATTERN, message.text):
        has_spam_link = True

    if has_spam_link:
        await message.reply("⛔️ **Alert**: Thambi ne sootha mootitu iru, inga link podatha.")
        return

    # --- AI TEXT REPLY ---
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    prompt = None
    if message.text:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser Message: {message.text}"
    elif message.photo:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser sent a photo with caption: '{message.caption or ''}'. Respond conversationally in Tanglish."
    elif message.video:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser sent a video with caption: '{message.caption or ''}'. Respond conversationally in Tanglish."
        
    if not prompt:
        return

    try:
        response = model.generate_content(prompt)
        ai_reply = response.text
        await message.reply(ai_reply)
    except Exception as e:
        print(f"[AI] Reply generate pannumbothu error: {e}")


# --- SCHEDULED GREETING FUNCTIONS ---
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    """Scheduled greeting ah generate panni send pannum."""
    if not model:
        return

    greeting_prompt = (
        f"You are the friendly group member 'Gemini'. Write a brief, cheerful "
        f"'{message_type}' greeting for the group chat. Keep it natural and short. "
        f"IMPORTANT: You must write the greeting in Tanglish (a mix of Tamil and English). "
    )

    try:
        response = model.generate_content(greeting_prompt)
        await client.send_message(chat_id, response.text)
    except Exception as e:
        print(f"[AI] {chat_id} ku scheduled greeting send pannumbothu error: {e}")
