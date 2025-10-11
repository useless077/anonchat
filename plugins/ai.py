# plugins/ai.py

import asyncio
import random
import re
from datetime import datetime, time, timedelta
from groq import Groq
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import GROQ_API_KEY, ADMIN_IDS
from database.users import db

# --- GROQ MODEL SELECTION ---
GROQ_MODEL_NAME = "llama-3.3-70b-versatile"

# --- GLOBAL STATE ---
ai_enabled_groups = set()
sticker_cache = set()
gif_cache = set()
consecutive_media_count = {}

# --- AI INITIALIZATION ---
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print(f"[AI] Groq client initialized successfully with model: {GROQ_MODEL_NAME}")
except Exception as e:
    print(f"[AI] Error initializing Groq client: {e}")
    groq_client = None

# --- AI PERSONALITY PROMPT ---
AI_PERSONA_PROMPT = (
    "You are 'Groq' — unga friend-maari pesura chill Tamil guy. "
    "Talk in **Tanglish** (Tamil + English mix) like normal Telegram group members. "
    "Be witty, short, natural, and human — no robotic or assistant tone. "
    "Use casual Tamil slang (machi, da, dei, super, seri, etc.) but not too much. "
    "Never translate literally — reply like how a normal Tamil person would chat online. "
    "Example style:\n"
    "- 'Enna da scene'\n"
    "- 'Semma da!'\n"
    "- 'Appo na sollurathu correct dhan 😎'\n"
    "- 'Haha, naanum adha nenachen 😂'\n"
    "Keep it fun and conversational, not like Q&A."
)

URL_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+)'

# --- 1. MEDIA CACHE HANDLER ---
@Client.on_message(filters.group & (filters.sticker | filters.animation))
async def cache_media(client: Client, message: Message):
    if message.from_user and message.from_user.is_bot:
        return
    if message.sticker and message.sticker.file_id:
        sticker_cache.add(message.sticker.file_id)
    elif message.animation and message.animation.file_id:
        gif_cache.add(message.animation.file_id)

# --- 2. /ai on | /ai off ---
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
        await message.reply("❌ Only admin or bot owner can use this.")
        return

    if len(message.command) < 2:
        await message.reply("Usage: `/ai on` or `/ai off`")
        return

    status = message.command[1].lower()
    if status == "on":
        ai_enabled_groups.add(chat_id)
        await db.set_ai_status(chat_id, True)
        await message.reply("✅ **AI Chatbot ON** aagiduchu!\nNaanum ippo group la pesuren 😎")
    elif status == "off":
        ai_enabled_groups.discard(chat_id)
        await db.set_ai_status(chat_id, False)
        await message.reply("🛑 **AI Chatbot OFF** aagiduchu.")
    else:
        await message.reply("Use `/ai on` or `/ai off` correctly da.")

# --- 3. MAIN AI HANDLER ---
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

    # --- Check if direct interaction ---
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.is_self
    )
    is_direct_interaction = is_reply_to_bot or (
        message.text and (f"@{client.username}" in message.text)
    )
    if not is_direct_interaction:
        if random.random() < 0.5:
            return

    # --- MEDIA REACTIONS ---
    current_count = consecutive_media_count.get(chat_id, 0)
    is_user_media = bool(message.sticker or message.animation)

    if is_user_media:
        choice = random.random()
        if choice < 0.7 and (sticker_cache or gif_cache):
            if sticker_cache and (not gif_cache or random.choice([True, False])):
                await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message.id)
            elif gif_cache:
                await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message.id)
            consecutive_media_count[chat_id] = current_count + 1
            return

        funny_lines = [
            "Haha adhukku oru sticker podanum da 😂",
            "Semma da, idhuku sticker dhan answer 😎",
            "Oru reaction venum pola iruku 😆",
            "Haha apdiya! Na sticker podren 🤭",
        ]
        text_reply = random.choice(funny_lines)
        await message.reply(text_reply)
        if sticker_cache:
            await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message.id)
        return

    consecutive_media_count[chat_id] = 0

    # --- SPAM/LINK CHECK ---
    is_sender_admin = False
    try:
        member = await client.get_chat_member(chat_id, message.from_user.id)
        if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            is_sender_admin = True
    except Exception:
        pass

    if not is_sender_admin and message.text and re.search(URL_PATTERN, message.text):
        await message.reply("⛔️ **Alert**: Thambi, inga link podatha.")
        return

    # --- AI REPLY ---
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    messages = [{"role": "system", "content": AI_PERSONA_PROMPT}]
    if message.text:
        messages.append({
            "role": "user",
            "content": f"Group member said: '{message.text}'. Respond casually and naturally in Tanglish, like you're chatting with friends."
        })
    elif message.photo:
        messages.append({"role": "user", "content": f"User sent a photo with caption: '{message.caption or ''}'. React funnily in Tanglish."})
    elif message.video:
        messages.append({"role": "user", "content": f"User sent a video with caption: '{message.caption or ''}'. React casually in Tanglish."})
    elif message.animation or message.sticker:
        media_type = "GIF" if message.animation else "Sticker"
        messages.append({"role": "user", "content": f"User sent a {media_type}. React with a short, funny Tanglish line."})
    else:
        return

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=messages,
            temperature=0.7,
            max_tokens=400
        )
        ai_reply = response.choices[0].message.content
        await asyncio.sleep(random.uniform(1.0, 2.5))
        await message.reply(ai_reply)
    except Exception as e:
        print(f"[AI] Reply error: {e}")
        if "rate" in str(e).lower() or "quota" in str(e).lower():
            await message.reply("🔥 Romba pesureenga! Oru nimisham wait pannunga...")
        elif "model_decommissioned" in str(e) or "404" in str(e) or "400" in str(e):
            await message.reply("⚠️ AI model update pannanum. Admin ah contact pannunga.")
        else:
            await message.reply("Sorry, enaku oru problem varudhu. Try pannunga!")

# --- 4. GREETING MESSAGE FUNCTION ---
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    if not groq_client:
        return
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are 'Groq', a friendly Tanglish group member. Keep greetings short and funny."},
                {"role": "user", "content": f"Write a '{message_type}' greeting in Tanglish for the group."}
            ],
            temperature=0.8,
            max_tokens=100
        )
        await client.send_message(chat_id, response.choices[0].message.content)
    except Exception as e:
        print(f"[AI] Greeting send error ({chat_id}): {e}")

# --- 5. AUTO GREETING SCHEDULER ---
async def auto_greeting_scheduler(client: Client):
    """Runs in background, sends morning/night greetings to AI-enabled groups."""
    await asyncio.sleep(10)
    while True:
        try:
            now = datetime.now().time()
            # 07:30 Morning, 22:30 Night
            morning_time = time(7, 30)
            night_time = time(22, 30)

            # Get all AI-enabled groups from DB
            groups = await db.get_all_ai_enabled_groups()
            if not groups:
                await asyncio.sleep(300)
                continue

            if morning_time <= now <= (datetime.combine(datetime.today(), morning_time) + timedelta(minutes=5)).time():
                for group_id in groups:
                    await send_greeting_message(client, group_id, "good morning")
            elif night_time <= now <= (datetime.combine(datetime.today(), night_time) + timedelta(minutes=5)).time():
                for group_id in groups:
                    await send_greeting_message(client, group_id, "good night")

            await asyncio.sleep(300)  # Check every 5 minutes
        except Exception as e:
            print(f"[AI Scheduler] Error: {e}")
            await asyncio.sleep(300)

# --- 6. START SCHEDULER WHEN BOT STARTS ---
@Client.on_startup
async def start_scheduler(client: Client):
    asyncio.create_task(auto_greeting_scheduler(client))
    print("[AI] Auto greeting scheduler started successfully ✅")
