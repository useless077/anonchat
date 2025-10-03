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

# Cache to track how many consecutive stickers/gifs the bot has sent per chat.
# Logic: If user sends media, bot replies with media up to 3 times, then switches to text.
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
# Indha handler, user-ah send panna stickers/GIFs-ah cache la store pannum.
# Bot-um yaarukum media send panna, athu cache-ah use pannum.
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

    # --- 2. LINK/URL CHECK ---
    # Message la URL irukka nu check pannum. Iruntha, special reply panni exit pannum.
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
        
    # --- 3. RANDOM CHANCE LOGIC (50% for non-replies / non-mentions) ---
    # Bot-ah mention pannala ya reply pannala, 50% chance la mattum reply pannum.
    is_direct_interaction = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    ) or (
        message.text and (f"@{client.username}" in message.text or client.username in message.text)
    )

    if not is_direct_interaction:
        if random.random() < 0.50: 
            return # Skip responding to keep it human-like

    # --- 4. STATE-BASED MEDIA/TEXT LOGIC ---
    current_count = consecutive_media_count.get(chat_id, 0)
    is_user_media = bool(message.sticker or message.animation)

    if is_user_media and (sticker_cache or gif_cache):
        # User sent media, check if we should continue the media streak (max 3)
        if current_count < 3: 
            media_sent = False
            # Randomly choose sticker or GIF from cache
            if sticker_cache and (not gif_cache or random.choice([True, False])): 
                media_id = random.choice(list(sticker_cache))
                await client.send_sticker(chat_id, media_id, reply_to_message_id=message.id)
                media_sent = True
            elif gif_cache:
                media_id = random.choice(list(gif_cache))
                await client.send_animation(chat_id, media_id, reply_to_message_id=message.id)
                media_sent = True
                
            if media_sent:
                consecutive_media_count[chat_id] = current_count + 1
                return # Media sent, STOP processing
            
    # If media streak is over OR user sent text, reset and proceed to text reply.
    consecutive_media_count[chat_id] = 0
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    # --- 5. AI reply ah generate pannrom ---
    prompt = None
    if message.text:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser Message: {message.text}"
    elif message.photo:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser sent a photo with caption: '{message.caption or ''}'. Respond conversationally in Tanglish."
    elif message.animation:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser sent a GIF. Acknowledge the GIF's mood/theme and respond conversationally in Tanglish."
    elif message.sticker:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser sent a sticker. Analyze the sticker's implied emotion and respond conversationally in Tanglish."
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
        f"IMPORTANT: You must write the greeting in Tanglish (a mix of Tamil and English)."
    )
    try:
        response = model.generate_content(greeting_prompt)
        await client.send_message(chat_id, response.text)
    except Exception as e:
        print(f"[AI] {chat_id} ku scheduled greeting send pannumbothu error: {e}")
