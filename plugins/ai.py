# plugins/ai.py

import asyncio
import random
import re
from datetime import datetime, time
from collections import deque
from groq import Groq
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import GROQ_API_KEY, ADMIN_IDS
from database.users import db

# --- MODEL NAME ---
# CORRECTED: This is a valid Groq model name.
GROQ_MODEL_NAME = "llama3-70b-8192"

# --- GLOBAL STATE ---
ai_enabled_groups = set()
# IMPROVEMENT: Using deque with a maxlen to prevent memory issues.
sticker_cache = deque(maxlen=50)
gif_cache = deque(maxlen=50)

# --- INIT GROQ CLIENT ---
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print(f"[AI] Groq client initialized successfully with model: {GROQ_MODEL_NAME}")
except Exception as e:
    print(f"[AI] Groq init error: {e}")
    groq_client = None

# --- PERSONA ---
# The persona will now be created dynamically inside the functions
# to use the bot's actual name.

URL_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+)'

# --- Flags for Greeting System ---
greeting_morning_sent = False
greeting_night_sent = False

# ==========================================================
#  /ai ON | OFF
# ==========================================================
@Client.on_message(filters.command("ai") & filters.group)
async def ai_toggle(client: Client, message: Message):
    chat_id = message.chat.id
    sender = message.from_user

    try:
        member = await client.get_chat_member(chat_id, sender.id)
        is_admin = member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        is_admin = False

    is_owner = sender.id in ADMIN_IDS if isinstance(ADMIN_IDS, (list, tuple, set)) else sender.id == ADMIN_IDS

    if not (is_owner or is_admin):
        await message.reply("❌ Only group admin or bot owner use panna mudiyum bro 😅")
        return

    if len(message.command) < 2:
        await message.reply("Usage: `/ai on` or `/ai off`")
        return

    status = message.command[1].lower()
    if status == "on":
        ai_enabled_groups.add(chat_id)
        await db.set_ai_status(chat_id, True)
        await message.reply("✅ **AI ON** — Groq vandhachu bro 😎")
    elif status == "off":
        ai_enabled_groups.discard(chat_id)
        await db.set_ai_status(chat_id, False)
        await message.reply("🛑 **AI OFF** — Groq break eduthukkan 😴")
    else:
        await message.reply("Use `/ai on` or `/ai off` correctly.")


# ==========================================================
#  NEW MEMBER WELCOME HANDLER
# ==========================================================
@Client.on_message(filters.service & filters.new_chat_members)
async def welcome_new_member(client: Client, message: Message):
    """Greets new users with a custom message if AI is enabled."""
    chat_id = message.chat.id

    # Check if AI is enabled in the group
    if not await db.get_ai_status(chat_id):
        return

    # Avoid greeting other bots
    new_users = [user for user in message.new_chat_members if not user.is_bot]
    if not new_users:
        return

    # Send the exact requested greeting
    await message.reply("Hyy akka vanthurukken daa 👄")


# ==========================================================
#  MEDIA CACHE HANDLER
# ==========================================================
@Client.on_message(filters.group & (filters.sticker | filters.animation))
async def cache_media(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    if message.sticker:
        sticker_cache.append(message.sticker.file_id)
    elif message.animation:
        gif_cache.append(message.animation.file_id)


# ==========================================================
#  MAIN AI RESPONDER
# ==========================================================
@Client.on_message(filters.group & ~filters.command)
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

    # --- Create a dynamic persona using the bot's name ---
    bot_name = client.me.first_name
    persona_prompt = (
        f"You are {bot_name} — a witty Tamil-English (Tanglish) Telegram group friend. "
        "Talk casually, like a human with emotions, humor, and natural slang. "
        "Avoid robotic tone. Keep it short, funny, and engaging."
    )

    # --- Interaction detection ---
    is_reply_to_bot = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    )
    is_tagged = (
        message.text
        and (f"@{client.username}" in message.text or client.username in message.text)
    )
    direct_interaction = is_reply_to_bot or is_tagged

    # --- Random filter for untagged messages ---
    if not direct_interaction and random.random() < 0.5:
        return

    # --- Sticker/GIF replies ---
    if message.sticker or message.animation:
        if sticker_cache or gif_cache:
            if sticker_cache and gif_cache:
                if random.choice([True, False]):
                    await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message.id)
                else:
                    await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message.id)
            elif sticker_cache:
                await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message.id)
            elif gif_cache:
                await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message.id)
        else:
            await message.reply(random.choice([
                "😂 semma sticker da!",
                "🔥 idhu vera level reaction!",
                "😎 haha nice da!"
            ]))
        return

    # --- Spam / Link Filter ---
    try:
        member = await client.get_chat_member(chat_id, message.from_user.id)
        is_admin = member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except Exception:
        is_admin = False

    has_link = bool(re.search(URL_PATTERN, message.text or ""))
    if has_link and not is_admin:
        await message.reply("⛔️ Link podatha bro, inga clean ah vaikkalam 😅")
        return

    # --- Generate Reply (Text or Sticker/GIF mix) ---
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    if direct_interaction and random.random() < 0.4 and (sticker_cache or gif_cache):
        if sticker_cache and gif_cache:
            if random.choice([True, False]):
                await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message.id)
            else:
                await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message.id)
        elif sticker_cache:
            await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message.id)
        elif gif_cache:
            await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message.id)
        return

    # --- Text Reply from Groq ---
    messages = [{"role": "system", "content": persona_prompt}]
    user_msg = message.text or message.caption or "User sent media."
    messages.append({"role": "user", "content": user_msg})

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        ai_reply = response.choices[0].message.content
        await message.reply(ai_reply)
    except Exception as e:
        print(f"[AI] Reply error: {e}")
        await message.reply("⚠️ Groq ku oru glitch vandhuduchu bro 😅 later try pannunga!")


# ==========================================================
#  AUTO GREETING SYSTEM (IMPROVED)
# ==========================================================
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    if not groq_client:
        return
    try:
        # Use bot's name here as well
        bot_name = client.me.first_name
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=[
                {"role": "system", "content": f"You are {bot_name}, a cheerful Tamil-English (Tanglish) friend."},
                {"role": "user", "content": f"Write a short '{message_type}' greeting in Tanglish with emojis."}
            ],
            temperature=0.8,
            max_tokens=60,
        )
        await client.send_message(chat_id, response.choices[0].message.content)
    except Exception as e:
        print(f"[AI] Greeting error in {chat_id}: {e}")


async def greeting_scheduler(client: Client):
    global greeting_morning_sent, greeting_night_sent
    while True:
        now = datetime.now()
        current_time = now.time()
        
        # Reset flags daily at midnight
        if current_time.hour == 0 and current_time.minute == 0:
            greeting_morning_sent = False
            greeting_night_sent = False

        # Morning greeting window (7:30 AM - 7:31 AM)
        morning_time = time(7, 30)
        if morning_time <= current_time <= time(7, 31) and not greeting_morning_sent:
            print("[AI] Sending morning greetings...")
            groups = await db.get_all_ai_enabled_groups()
            for gid in groups:
                await send_greeting_message(client, gid, "Good morning")
            greeting_morning_sent = True

        # Night greeting window (10:30 PM - 10:31 PM)
        night_time = time(22, 30)
        if night_time <= current_time <= time(22, 31) and not greeting_night_sent:
            print("[AI] Sending night greetings...")
            groups = await db.get_all_ai_enabled_groups()
            for gid in groups:
                await send_greeting_message(client, gid, "Good night")
            greeting_night_sent = True
        
        await asyncio.sleep(50) # Check every 50 seconds


# --- Function to be called from main.py ---
async def start_greeting_task(client: Client):
    print("[AI] Starting greeting scheduler task.")
    asyncio.create_task(greeting_scheduler(client))
