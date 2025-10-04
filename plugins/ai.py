# plugins/ai.py

import asyncio
import random
import re
from groq import Groq
from pyrogram import Client, filters, enums
from pyrogram.types import Message
# Ensure these imports match your actual config file
from config import GROQ_API_KEY, ADMIN_IDS 
from database.users import db 

# --- GROQ MODEL SELECTION ---
# Please replace this with the latest *supported* Groq model name from your dashboard.
# Recommended current model for best performance/speed trade-off: llama3-70b-8192-pro
GROQ_MODEL_NAME = "llama3-70b-8192-pro" 

# --- AI INITIALIZATION ---
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print(f"[AI] Groq AI client successful-a initialize aagiduchu with model: {GROQ_MODEL_NAME}!")
except Exception as e:
    print(f"[AI] Groq AI initialize pannumbothu error: {e}")
    groq_client = None

# --- GLOBAL CACHE AND STATE MANAGEMENT ---
sticker_cache = set()
gif_cache = set()
consecutive_media_count = {}
# Using DB status for AI enabled groups is better than a separate set
# ai_enabled_groups = set() 

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

# -----------------------------------------------------------
## 1. MEDIA CACHE HANDLER
# -----------------------------------------------------------
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

# -----------------------------------------------------------
## COMMAND HANDLER (/ai on | /ai off)
# -----------------------------------------------------------
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
        # ai_enabled_groups.add(chat_id) # Using DB is better
        await db.set_ai_status(chat_id, True)
        await message.reply("✅ **AI Chatbot ipo ON** aagiduchu.\nNaanum conversation la join pannuren!")
    elif status == "off":
        # ai_enabled_groups.discard(chat_id) # Using DB is better
        await db.set_ai_status(chat_id, False)
        await message.reply("🛑 **AI Chatbot ipo OFF** aagiduchu.")
    else:
        await message.reply("Correct ah use pannunga. `/ai on` ya `/ai off`.")

# -----------------------------------------------------------
## MAIN AI MESSAGE HANDLER
# -----------------------------------------------------------
@Client.on_message(filters.group & ~filters.command(["ai", "start", "search", "next", "end", "myprofile", "profile"]))
async def ai_responder(client: Client, message: Message):
    if not groq_client:
        return

    chat_id = message.chat.id
    if not await db.get_ai_status(chat_id):
        return

    if message.from_user and message.from_user.is_bot:
        return
        
    if message.text and message.text.startswith('/'):
        return

    # --- 2. RANDOM CHANCE LOGIC (50% / 100%) ---
    is_reply_to_bot = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    )

    is_direct_interaction = is_reply_to_bot or (
        message.text and (f"@{client.username}" in message.text or client.username in message.text)
    )

    if not is_direct_interaction:
        if random.random() < 0.50: 
            return # 50% chance skip for general chat

    # --- 3. STATE-BASED MEDIA/TEXT LOGIC (3 by 1 method) ---
    current_count = consecutive_media_count.get(chat_id, 0)
    is_user_media = bool(message.sticker or message.animation)

    if is_user_media and (sticker_cache or gif_cache):
        # User sent media, check if we should continue the media streak (max 3)
        if current_count < 3: 
            media_sent = False
            
            # Send Sticker (50% chance or if only sticker cache is available)
            if sticker_cache and (not gif_cache or random.choice([True, False])): 
                media_id = random.choice(list(sticker_cache))
                await client.send_sticker(chat_id, media_id, reply_to_message_id=message.id)
                media_sent = True
            # Send GIF (if sticker was not sent or if GIF cache is available)
            elif gif_cache:
                media_id = random.choice(list(gif_cache))
                await client.send_animation(chat_id, media_id, reply_to_message_id=message.id)
                media_sent = True
                
            if media_sent:
                consecutive_media_count[chat_id] = current_count + 1
                return # Media sent, STOP processing
            
    # Reset streak here, as we are proceeding to a text reply (end of 3 media or user sent text)
    consecutive_media_count[chat_id] = 0

    # --- 4. LINK/URL CHECK (Admin Exception Added) ---
    is_sender_admin = False
    try:
        member = await client.get_chat_member(chat_id, message.from_user.id)
        # Check for OWNER or ADMINISTRATOR status
        if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            is_sender_admin = True
    except Exception:
        # Fails if user is anonymous or bot is not admin in the group
        # No need to raise an error, just continue as is_sender_admin remains False
        pass 
        
    has_spam_link = False
    if message.entities:
        for entity in message.entities:
            if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                has_spam_link = True
                break
                
    if message.text and re.search(URL_PATTERN, message.text):
        has_spam_link = True

    # Block link ONLY IF it's a spam link AND the sender is NOT an admin
    if has_spam_link and not is_sender_admin:
        await message.reply("⛔️ **Alert**: Thambi ne sootha mootitu iru, inga link podatha.")
        return

    # --- 5. AI TEXT REPLY GENERATION ---
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    # Groq API call messages setup
    messages = [{"role": "system", "content": AI_PERSONA_PROMPT}]
    
    # Determine user message based on content type
    if message.text:
        messages.append({"role": "user", "content": message.text})
    elif message.photo:
        messages.append({"role": "user", "content": f"User sent a photo with caption: '{message.caption or ''}'. Analyze the context and respond conversationally in Tanglish."})
    elif message.video:
        messages.append({"role": "user", "content": f"User sent a video with caption: '{message.caption or ''}'. Respond conversationally in Tanglish."})
    elif message.animation or message.sticker:
        # This is the text reply after the media streak or if media cache was empty
        media_type = "GIF" if message.animation else "Sticker"
        messages.append({"role": "user", "content": f"User just sent a {media_type}. Acknowledge it with a witty Tanglish reply, as we are switching back to text mode."})
    else:
        return

    try:
        # Groq API call with the CURRENTLY SUPPORTED model name
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME, 
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        ai_reply = response.choices[0].message.content
        await message.reply(ai_reply)

    except Exception as e:
        print(f"[AI] Reply generate pannumbothu error: {e}")
        # Log specific error if it's related to model decommissioning or API
        if "decommissioned" in str(e).lower() or "400" in str(e).lower():
            await message.reply("🛑 **API Error:** Ennoda AI model (Groq) decommission aagiduchu. Owner'ah contact panni `GROQ_MODEL_NAME`-ah update panna sollunga.")
        elif "rate" in str(e).lower() or "quota" in str(e).lower():
            await message.reply("🔥 Romba pesureenga! Oru nimisham wait pannunga...")
        else:
            # Fallback for other errors
            await message.reply("Sorry, enaku oru problem varudhu. Try pannunga!")

# -----------------------------------------------------------
## SCHEDULED GREETING FUNCTIONS
# -----------------------------------------------------------
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    """Scheduled greeting ah generate panni send pannum."""
    if not groq_client:
        return

    try:
        # Groq API call for greetings
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME, # Use the defined working model name
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
