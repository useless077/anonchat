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
GROQ_MODEL_NAME = "llama-3.3-70b-versatile"

# --- GLOBAL STATE ---
ai_enabled_groups = set()
sticker_cache = deque(maxlen=50)
gif_cache = deque(maxlen=50)

# --- INIT GROQ CLIENT ---
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print(f"[AI] Groq client initialized successfully with model: {GROQ_MODEL_NAME}")
except Exception as e:
    print(f"[AI] Groq init error: {e}")
    groq_client = None

URL_PATTERN = r'(https?://\S+|t\.me/\S+|telegram\.me/\S+)'

# --- Flags for Greeting System ---
greeting_morning_sent = False
greeting_night_sent = False

# ==========================================================
# ✨ Fancy Font Converter ✨
# ==========================================================
FANCY_FONT_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ',
    'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ',
    'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ', 'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ',
    'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ', 'S': 'ꜱ', 'T': 'ᴛ',
    'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
}

def to_fancy_font(text: str) -> str:
    """Converts a string to the fancy small-caps font."""
    fancy_text = []
    for char in text:
        fancy_text.append(FANCY_FONT_MAP.get(char, char))
    return "".join(fancy_text)

def remove_emojis(text: str) -> str:
    """Remove emojis from bot's responses only (not user messages)."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub(r'', text).strip()

def should_use_emojis() -> bool:
    """Randomly decide if emojis should be used (30-40% chance)."""
    return random.random() < 0.35  # 35% chance

# ==========================================================
#  /ai ON | OFF (OWNER ONLY)
# ==========================================================
@Client.on_message(filters.command("ai") & filters.group)
async def ai_toggle(client: Client, message: Message):
    chat_id = message.chat.id
    sender = message.from_user

    is_owner = sender.id in ADMIN_IDS if isinstance(ADMIN_IDS, (list, tuple, set)) else sender.id == ADMIN_IDS

    if not is_owner:
        await message.reply("❌ Only the bot owner can use this command.")
        return

    if len(message.command) < 2:
        await message.reply("Usage: `/ai on` or `/ai off`")
        return

    status = message.command[1].lower()
    if status == "on":
        ai_enabled_groups.add(chat_id)
        await db.set_ai_status(chat_id, True)
        await message.reply("✅ **AI ON** — Bot is ready to talk! 😎")
    elif status == "off":
        ai_enabled_groups.discard(chat_id)
        await db.set_ai_status(chat_id, False)
        await message.reply("🛑 **AI OFF** — Bot is taking a break. 😴")
    else:
        await message.reply("Use `/ai on` or `/ai off` correctly.")

# ==========================================================
#  NEW MEMBER WELCOME HANDLER
# ==========================================================
@Client.on_message(filters.service & filters.new_chat_members)
async def welcome_new_member(client: Client, message: Message):
    """Greets new users with a custom message if AI is enabled."""
    chat_id = message.chat.id

    if not await db.get_ai_status(chat_id):
        return

    new_users = [user for user in message.new_chat_members if not user.is_bot]
    if not new_users:
        return

    # Generate personalized welcome messages for each new user
    for user in new_users:
        try:
            bot_name = client.me.first_name
            user_name = user.first_name
            use_emojis = should_use_emojis()
            emoji_instruction = "Use appropriate emojis" if use_emojis else "Do not use any emojis"
            
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL_NAME,
                messages=[
                    {"role": "system", "content": f"You are {bot_name}, a witty Tamil-English (Tanglish) Telegram group friend."},
                    {"role": "user", "content": f"Write a funny, personalized welcome message for {user_name} who just joined the group. Use Tanglish. {emoji_instruction}. Keep it short and engaging."}
                ],
                temperature=0.8,
                max_tokens=100,
            )
            welcome_text = response.choices[0].message.content
            if not use_emojis:
                welcome_text = remove_emojis(welcome_text)
            fancy_welcome = to_fancy_font(welcome_text)
            await message.reply(fancy_welcome)
        except Exception as e:
            print(f"[AI] Welcome message error: {e}")
            # Fallback to the specific message if AI fails
            welcome_text = "Hyy akka vanthurukken daa 👄" if should_use_emojis() else "Hyy akka vanthurukken daa"
            if not should_use_emojis():
                welcome_text = remove_emojis(welcome_text)
            fancy_welcome = to_fancy_font(welcome_text)
            await message.reply(fancy_welcome)

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
#  AI REPLY GENERATOR HELPER
# ==========================================================
async def generate_ai_reply(client: Client, message: Message, user_input: str) -> str:
    """Generate AI reply using Groq with the bot's persona."""
    bot_name = client.me.first_name
    use_emojis = should_use_emojis()
    emoji_instruction = "Use appropriate emojis" if use_emojis else "Do not use any emojis"
    persona_prompt = (
        f"You are {bot_name} — a witty Tamil-English (Tanglish) Telegram group friend. "
        "Talk casually, like a human with emotions, humor, and natural slang. "
        "Avoid robotic tone. Keep it short, funny, and engaging. "
        f"{emoji_instruction}."
    )
    
    messages = [{"role": "system", "content": persona_prompt}]
    messages.append({"role": "user", "content": user_input})

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        ai_reply = response.choices[0].message.content
        if not use_emojis:
            ai_reply = remove_emojis(ai_reply)
        return ai_reply
    except Exception as e:
        print(f"[AI] Reply error: {e}")
        return "⚠️ Oru glitch vandhuduchu bro 😅 later try pannunga!" if should_use_emojis() else "⚠️ Oru glitch vandhuduchu bro later try pannunga!"

# ==========================================================
#  MAIN AI RESPONDER (FINAL & BEST VERSION)
# ==========================================================
@Client.on_message(filters.group & ~filters.command(["ai", "autodelete", "start", "search", "next", "end", "myprofile", "profile"]))
async def ai_responder(client: Client, message: Message):
    if not groq_client:
        return
    chat_id = message.chat.id
    if not await db.get_ai_status(chat_id):
        return
    if message.from_user and message.from_user.is_bot:
        return

    is_reply_to_bot = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    )
    is_tagged = (
        message.text
        and (f"@{client.username}" in message.text or client.username in message.text)
    )
    direct_interaction = is_reply_to_bot or is_tagged

    # Check for specific messages and respond accordingly
    if message.text:
        text = message.text.lower()
        
        # Always respond with the specific message for "hi"
        if text == "hi":
            use_emojis = should_use_emojis()
            welcome_text = "Hyy akka vanthurukken daa 👄" if use_emojis else "Hyy akka vanthurukken daa"
            if not use_emojis:
                welcome_text = remove_emojis(welcome_text)
            fancy_welcome = to_fancy_font(welcome_text)
            await message.reply(fancy_welcome)
            return
        
        # Funny responses for other specific messages
        if text in ["bye", "sari", "kilampu"]:
            use_emojis = should_use_emojis()
            funny_responses = {
                "bye": [
                    "Bye da mapla! Varreenga pola! 👋" if use_emojis else "Bye da mapla! Varreenga pola!",
                    "Poitu varen da! Nalla irukka! 😊" if use_emojis else "Poitu varen da! Nalla irukka!",
                    "Bye bye machi! Next time pakkaalam! 🤝" if use_emojis else "Bye bye machi! Next time pakkaalam!"
                ],
                "sari": [
                    "Sari sari! Namma plan pannalam! 😎" if use_emojis else "Sari sari! Namma plan pannalam!",
                    "Sari da! Unaku vera venuma? 🤔" if use_emojis else "Sari da! Unaku vera venuma?",
                    "Sari sari! Puriyudhu! 👍" if use_emojis else "Sari sari! Puriyudhu!"
                ],
                "kilampu": [
                    "Kilampuda mapla! Nalaiku pakalam! 😴" if use_emojis else "Kilampuda mapla! Nalaiku pakalam!",
                    "Kilambu da! Nee yaarukum thevaiya? 😂" if use_emojis else "Kilambu da! Nee yaarukum thevaiya?",
                    "Kilambu da! Poi padu! 😴" if use_emojis else "Kilambu da! Poi padu!"
                ]
            }
            
            response = random.choice(funny_responses.get(text, []))
            if not use_emojis:
                response = remove_emojis(response)
            fancy_response = to_fancy_font(response)
            await message.reply(fancy_response)
            return

    if not direct_interaction and random.random() < 0.5:
        return

    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)

    # --- Handle Sticker/GIF replies with AI ---
    if message.sticker or message.animation:
        media_type = "sticker" if message.sticker else "GIF"
        use_emojis = should_use_emojis()
        emoji_instruction = "Use appropriate emojis" if use_emojis else "Do not use any emojis"
        user_input = f"User sent a {media_type}, reply in Tanglish as if you're reacting to it. {emoji_instruction}."
        
        ai_reply = await generate_ai_reply(client, message, user_input)
        fancy_ai_reply = to_fancy_font(ai_reply)
        
        await message.reply(fancy_ai_reply)
        return

    # --- Spam / Link Filter ---
    try:
        member = await client.get_chat_member(chat_id, message.from_user.id)
        is_admin = member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except Exception:
        is_admin = False

    has_link = bool(re.search(URL_PATTERN, message.text or ""))
    if has_link and not is_admin:
        use_emojis = should_use_emojis()
        await message.reply("⛔️ Link podatha bro, inga clean ah vaikkalam 😅" if use_emojis else "⛔️ Link podatha bro, inga clean ah vaikkalam")
        return

    # --- Random media reply for direct interaction ---
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
    user_msg = message.text or message.caption or "User sent media."
    ai_reply = await generate_ai_reply(client, message, user_msg)
    fancy_ai_reply = to_fancy_font(ai_reply)
    
    await message.reply(fancy_ai_reply)

# ==========================================================
#  AUTO GREETING SYSTEM
# ==========================================================
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    if not groq_client:
        return
    try:
        bot_name = client.me.first_name
        use_emojis = should_use_emojis()
        emoji_instruction = "Use appropriate emojis" if use_emojis else "Do not use any emojis"
        
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=[
                {"role": "system", "content": f"You are {bot_name}, a cheerful Tamil-English (Tanglish) friend."},
                {"role": "user", "content": f"Write a short '{message_type}' greeting in Tanglish. {emoji_instruction}."}
            ],
            temperature=0.8,
            max_tokens=60,
        )
        greeting_text = response.choices[0].message.content
        if not use_emojis:
            greeting_text = remove_emojis(greeting_text)
        fancy_greeting = to_fancy_font(greeting_text)
        
        await client.send_message(chat_id, fancy_greeting)
    except Exception as e:
        print(f"[AI] Greeting error in {chat_id}: {e}")

async def greeting_scheduler(client: Client):
    global greeting_morning_sent, greeting_night_sent
    while True:
        now = datetime.now()
        current_time = now.time()
        
        if current_time.hour == 0 and current_time.minute == 0:
            greeting_morning_sent = False
            greeting_night_sent = False

        morning_time = time(7, 30)
        if morning_time <= current_time <= time(7, 31) and not greeting_morning_sent:
            print("[AI] Sending morning greetings...")
            groups = await db.get_all_ai_enabled_groups()
            for gid in groups:
                await send_greeting_message(client, gid, "Good morning")
            greeting_morning_sent = True

        night_time = time(22, 30)
        if night_time <= current_time <= time(22, 31) and not greeting_night_sent:
            print("[AI] Sending night greetings...")
            groups = await db.get_all_ai_enabled_groups()
            for gid in groups:
                await send_greeting_message(client, gid, "Good night")
            greeting_night_sent = True
        
        await asyncio.sleep(50)

async def start_greeting_task(client: Client):
    print("[AI] Starting greeting scheduler task.")
    asyncio.create_task(greeting_scheduler(client))
