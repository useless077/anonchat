# plugins/ai.py

import asyncio
import random
import re
from groq import Groq  # <-- CHANGE: Gemini இலிருந்து Groq க்கு மாற்றம்
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import GROQ_API_KEY, ADMIN_IDS  # <-- CHANGE: GEMINI_API_KEY இலிருந்து GROQ_API_KEY
from database.users import db

# --- GLOBAL STATE FOR AI ---
ai_enabled_groups = set()

# --- AI INITIALIZATION ---
try:
    # CHANGE: Groq client initialization
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("[AI] Groq AI successful-a initialize aagiduchu!")
except Exception as e:
    print(f"[AI] Groq AI initialize pannumbothu error: {e}")
    groq_client = None

# --- GLOBAL CACHE AND STATE MANAGEMENT ---
sticker_cache = set()
gif_cache = set()
consecutive_media_count = {}

# --- AI KU PESUM STYLE (PERSONA PROMPT) ---
AI_PERSONA_PROMPT = (
    "You are a friendly, witty, and highly conversational Telegram group member "
    "named 'Groq'. Your goal is to engage in natural, human-like chat, "
    "keeping conversations flowing and responding to group dynamic. "
    "Do not act like a formal assistant. Keep your replies concise, witty, and relatable. "
    "IMPORTANT: You must always reply in Tanglish, which is a mix of Tamil and English. "
    "Your responses should feel natural to a Tamil-speaking audience."
)

# --- URL/LINK CHECKER PATTERN ---
URL_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+)'

# --- 1. MEDIA CACHE HANDLER ---
@Client.on_message(filters.group & (filters.sticker | filters.animation))
async def cache_media(client: Client, message: Message):
    if message.from_user and message.from_user.is_bot:
        return
        
    if message.sticker:
        sticker_file_id = message.sticker.file_id
        if sticker_file_id:
            sticker_cache.add(sticker_file_id)
    elif message.animation:
        gif_file_id = message.animation.file_id
        if gif_file_id:
            gif_cache.add(gif_file_id)

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
        ai_enabled_groups.add(chat_id)
        await db.set_ai_status(chat_id, True)
        await message.reply("✅ **AI Chatbot ipo ON** aagiduchu.\nNaanum conversation la join pannuren!")
    elif status == "off":
        ai_enabled_groups.discard(chat_id)
        await db.set_ai_status(chat_id, False)
        await message.reply("🛑 **AI Chatbot ipo OFF** aagiduchu.")
    else:
        await message.reply("Correct ah use pannunga. `/ai on` ya `/ai off`.")

# --- MAIN AI MESSAGE HANDLER ---
@Client.on_message(filters.group & ~filters.command(["ai", "start", "search", "next", "end", "myprofile", "profile"]))
async def ai_responder(client: Client, message: Message):
    if not groq_client:  # CHANGE: model இலிருந்து groq_client க்கு மாற்றம்
        return

    chat_id = message.chat.id
    if not await db.get_ai_status(chat_id):
        return

    if message.from_user and message.from_user.is_bot:
        return
        
    if message.text and message.text.startswith('/'):
        return

    # --- 2. RANDOM CHANCE LOGIC ---
    is_reply_to_bot = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    )

    is_direct_interaction = is_reply_to_bot or (
        message.text and (f"@{client.username}" in message.text or client.username in message.text)
    )

    if not is_direct_interaction:
        if random.random() < 0.50: 
            return

    # --- 3. STATE-BASED MEDIA/TEXT LOGIC ---
    current_count = consecutive_media_count.get(chat_id, 0)
    
    is_user_media = bool(message.sticker or message.animation)

    if is_user_media and (sticker_cache or gif_cache):
        if current_count < 3: 
            media_sent = False
            
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
                return
            
    consecutive_media_count[chat_id] = 0

    # --- 4. LINK/URL CHECK ---
    is_sender_admin = False
    try:
        member = await client.get_chat_member(chat_id, message.from_user.id)
        if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            is_sender_admin = True
    except Exception:
        pass 
        
    has_spam_link = False
    if message.entities:
        for entity in message.entities:
            if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                has_spam_link = True
                break
                
    if message.text and re.search(URL_PATTERN, message.text):
        has_spam_link = True

    if has_spam_link and not is_sender_admin:
        await message.reply("⛔️ **Alert**: Thambi ne sootha mootitu iru, inga link podatha.")
        return

    # --- 5. AI TEXT REPLY ---
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    # CHANGE: Groq API call format
    messages = [{"role": "system", "content": AI_PERSONA_PROMPT}]
    
    if message.text:
        messages.append({"role": "user", "content": message.text})
    elif message.photo:
        messages.append({"role": "user", "content": f"User sent a photo with caption: '{message.caption or ''}'. Analyze the context and respond conversationally in Tanglish."})
    elif message.video:
        messages.append({"role": "user", "content": f"User sent a video with caption: '{message.caption or ''}'. Respond conversationally in Tanglish."})
    elif message.animation or message.sticker:
        media_type = "GIF" if message.animation else "Sticker"
        messages.append({"role": "user", "content": f"User just sent a {media_type}. Acknowledge it with a witty Tanglish reply."})
    else:
        return

    try:
        # CHANGE: Groq API call
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",  # FIXED: Changed from decommissioned llama3-8b-8192 to llama3-70b-8192
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        ai_reply = response.choices[0].message.content
        await message.reply(ai_reply)

    except Exception as e:
        print(f"[AI] Reply generate pannumbothu error: {e}")
        # CHANGE: Better error handling for Groq
        if "rate" in str(e).lower() or "quota" in str(e).lower():
            await message.reply("🔥 Romba pesureenga! Oru nimisham wait pannunga...")
        else:
            await message.reply("Sorry, enaku oru problem varudhu. Try pannunga!")

# --- SCHEDULED GREETING FUNCTIONS ---
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    """Scheduled greeting ah generate panni send pannum."""
    if not groq_client:  # CHANGE: model இலிருந்து groq_client க்கு மாற்றம்
        return

    try:
        # CHANGE: Groq API call for greetings
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",  # FIXED: Changed from decommissioned llama3-8b-8192 to llama3-70b-8192
            messages=[
                {"role": "system", "content": "You are the friendly group member 'Groq'. Write brief, cheerful greetings in Tanglish."},
                {"role": "user", "content": f"Write a '{message_type}' greeting for the group."}
            ],
            temperature=0.7,
            max_tokens=100
        )
        await client.send_message(chat_id, response.choices[0].message.content)
    except Exception as e:
        print(f"[AI] {chat_id} ku scheduled greeting send pannumbothu error: {e}")
