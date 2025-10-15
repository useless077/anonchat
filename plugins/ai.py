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
from utils import autodelete_enabled_chats, schedule_deletion

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

def should_use_fancy_font() -> bool:
    """Randomly decide if fancy font should be used (15% chance)."""
    return random.random() < 0.15

# ==========================================================
#  Load AI State from DB (To be called in main.py on bot startup)
# ==========================================================
async def load_ai_state():
    """Loads all AI-enabled groups from the database into the global set."""
    global ai_enabled_groups
    try:
        all_enabled = await db.get_all_ai_enabled_chats()
        if all_enabled:
            ai_enabled_groups = set(all_enabled)
        print(f"[AI] Loaded {len(ai_enabled_groups)} AI-enabled groups from DB: {ai_enabled_groups}")
    except Exception as e:
        print(f"[AI] Error loading AI state from DB: {e}")

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
        print(f"[AI] Enabled AI in chat {chat_id}")
        await message.reply("✅ **AI ON** — Bot is ready to talk! 😎")
    elif status == "off":
        ai_enabled_groups.discard(chat_id)
        await db.set_ai_status(chat_id, False)
        print(f"[AI] Disabled AI in chat {chat_id}")
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

    is_ai_enabled = chat_id in ai_enabled_groups
    if not is_ai_enabled:
        try:
            is_ai_enabled = await db.get_ai_status(chat_id)
            if is_ai_enabled:
                ai_enabled_groups.add(chat_id)
                print(f"[AI] Updated in-memory set for chat {chat_id}")
        except Exception as e:
            print(f"[AI] Error checking AI status for chat {chat_id}: {e}")
            return
    
    if not is_ai_enabled:
        return

    new_users = [user for user in message.new_chat_members if not user.is_bot]
    if not new_users:
        return

    for user in new_users:
        try:
            bot_name = client.me.first_name
            user_name = user.first_name
            
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL_NAME,
                messages=[
                    {"role": "system", "content": f"You are {bot_name}, a witty Tamil-English (Tanglish) Telegram group friend. Your job is to generate a short, funny, and personalized welcome message for the new user."},
                    {"role": "user", "content": f"Write a funny, personalized welcome message for '{user_name}' who just joined the group. Use Tanglish slang with emojis. Keep it under 100 characters."}
                ],
                temperature=0.8,
                max_tokens=80,
            )
            welcome_text = response.choices[0].message.content
            
            if should_use_fancy_font():
                welcome_text = to_fancy_font(welcome_text)
            
            # --- CHANGE 1: Capture the message object for autodelete ---
            sent_message = await message.reply(welcome_text)

            # --- CHANGE 2: Schedule deletion if autodelete is enabled ---
            if chat_id in autodelete_enabled_chats and sent_message:
                asyncio.create_task(schedule_deletion(client, chat_id, [sent_message.id]))
                
        except Exception as e:
            print(f"[AI] Welcome message error: {e}")
            fallback_text = "Hyy akka vanthurukken daa 👋"
            if should_use_fancy_font():
                 fallback_text = to_fancy_font(fallback_text)
            
            # --- CHANGE 3: Capture the message object for autodelete ---
            sent_message = await message.reply(fallback_text)

            # --- CHANGE 4: Schedule deletion if autodelete is enabled ---
            if chat_id in autodelete_enabled_chats and sent_message:
                asyncio.create_task(schedule_deletion(client, chat_id, [sent_message.id]))

# ==========================================================
#  MEDIA CACHE HANDLER
# ==========================================================
@Client.on_message(filters.group & (filters.sticker | filters.animation))
async def cache_media(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    if message.sticker:
        sticker_cache.append(message.sticker.file_id)
        print(f"[AI] Cached sticker: {message.sticker.file_id}")
    elif message.animation:
        gif_cache.append(message.animation.file_id)
        print(f"[AI] Cached GIF: {message.animation.file_id}")

# ==========================================================
#  AI REPLY GENERATOR HELPER
# ==========================================================
async def generate_ai_reply(client: Client, message: Message, user_input: str) -> str:
    """Generate AI reply using Groq with the bot's persona."""
    if not groq_client:
        return "⚠️ Groq API not initialized. Check your API key in config.py!"
        
    bot_name = client.me.first_name
    use_emojis = should_use_emojis()
    emoji_instruction = "Use appropriate emojis" if use_emojis else "Do not use any emojis"
    persona_prompt = (
        f"You are {bot_name} — a witty Tamil-English (Tanglish) Telegram group friend. "
        "Talk casually, like a human with emotions, humor, and natural slang. "
        "Avoid robotic tone. Keep it short, funny, and engaging. "
        "Your replies should look like a real person reading and reacting to the conversation. "
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
#  MIXED RESPONSE HELPER (MODIFIED TO RETURN MESSAGE)
# ==========================================================
async def send_mixed_response(client: Client, chat_id: int, message_id: int, text_reply: str = None):
    """Send a mixed response with text, emojis, and possibly media. Returns the sent message object."""
    response_type = random.choice(["text_only", "text_emoji", "text_media", "media_only"])
    sent_message = None
    
    if response_type in ["text_only", "text_emoji"] and text_reply:
        if should_use_fancy_font():
            text_reply = to_fancy_font(text_reply)
        sent_message = await client.send_message(chat_id, text_reply, reply_to_message_id=message_id)
    
    elif response_type == "text_media" and text_reply:
        if should_use_fancy_font():
            text_reply = to_fancy_font(text_reply)
        sent_message = await client.send_message(chat_id, text_reply, reply_to_message_id=message_id)
        
        await asyncio.sleep(0.5)
        
        if sticker_cache and gif_cache:
            if random.choice([True, False]):
                await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message_id)
            else:
                await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message_id)
        elif sticker_cache:
            await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message_id)
        elif gif_cache:
            await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message_id)
    
    elif response_type == "media_only":
        # This is the part that was failing
        if sticker_cache and gif_cache:
            if random.choice([True, False]):
                sent_message = await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message_id)
            else:
                sent_message = await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message_id)
        elif sticker_cache:
            sent_message = await client.send_sticker(chat_id, random.choice(list(sticker_cache)), reply_to_message_id=message_id)
        elif gif_cache:
            sent_message = await client.send_animation(chat_id, random.choice(list(gif_cache)), reply_to_message_id=message_id)
        else:
            # --- FIX 1: If cache is empty, fall back to text reply ---
            if text_reply:
                if should_use_fancy_font():
                    text_reply = to_fancy_font(text_reply)
                sent_message = await client.send_message(chat_id, text_reply, reply_to_message_id=message_id)

    # --- FIX 2: If nothing was sent for any reason, send the text as a last resort ---
    if not sent_message and text_reply:
        if should_use_fancy_font():
            text_reply = to_fancy_font(text_reply)
        sent_message = await client.send_message(chat_id, text_reply, reply_to_message_id=message_id)

    return sent_message


# ==========================================================
#  MAIN AI RESPONDER (MODIFIED FOR AUTODELETE)
# ==========================================================
@Client.on_message(filters.group & ~filters.command(["ai", "autodelete", "start", "search", "next", "end", "myprofile", "profile"]))
async def ai_responder(client: Client, message: Message):
    if not groq_client:
        return
        
    chat_id = message.chat.id
    
    is_ai_enabled = chat_id in ai_enabled_groups
    if not is_ai_enabled:
        try:
            is_ai_enabled = await db.get_ai_status(chat_id)
            if is_ai_enabled:
                ai_enabled_groups.add(chat_id)
                print(f"[AI] Updated in-memory set for chat {chat_id}")
        except Exception as e:
            print(f"[AI] Error checking AI status for chat {chat_id}: {e}")
            return
    
    if not is_ai_enabled:
        print(f"[AI] AI not enabled in chat {chat_id}")
        return
        
    if message.from_user and message.from_user.is_bot:
        print(f"[AI] Ignoring bot message")
        return

    is_reply_to_bot = bool(
        message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self
    )
    is_tagged = (
        message.text
        and (f"@{client.username}" in message.text or client.username in message.text)
    )
    direct_interaction = is_reply_to_bot or is_tagged

    print(f"[AI] Processing message: {message.text or 'Media'} from {message.from_user.first_name} in chat {chat_id}")
    print(f"[AI] Direct interaction: {direct_interaction}, Sticker: {bool(message.sticker)}, GIF: {bool(message.animation)}")

    bot_message = None
    ai_reply_text = None

    # --- 1. Handle Sticker/GIF replies ---
    if message.sticker or message.animation:
        media_type = "sticker" if message.sticker else "GIF"
        ai_reply_text = await generate_ai_reply(client, message, f"User sent a {media_type}, react to it in Tanglish.")
    
    # --- 2. Handle Hardcoded Text Responses ---
    elif message.text:
        text = message.text.lower()
        if text == "hi": ai_reply_text = await generate_ai_reply(client, message, "User said 'hi', greet them back in a funny way in Tanglish.")
        elif text in ["bye", "sari", "kilampu"]: ai_reply_text = await generate_ai_reply(client, message, f"User said '{text}', respond in a funny way in Tanglish.")

    # --- 3. Handle Tagged Messages ---
    if direct_interaction and not ai_reply_text:
        user_msg = message.text or message.caption or "User sent media."
        ai_reply_text = await generate_ai_reply(client, message, f"User tagged you or replied to you: '{user_msg}', respond in a funny way in Tanglish.")

    # --- 4. Handle Random Interactions ---
    if not direct_interaction and not ai_reply_text and random.random() > 0.5: return
    if not ai_reply_text:
        await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
        user_msg = message.text or message.caption or "User sent media."
        ai_reply_text = await generate_ai_reply(client, message, user_msg)

    # --- 5. Send Response and Schedule Deletion ---
    if ai_reply_text:
        # --- CHANGE 12: Capture the returned message object ---
        bot_message = await send_mixed_response(client, chat_id, message.id, ai_reply_text)

    # --- CHANGE 13: INTEGRATE WITH AUTODELETE ---
    if chat_id in autodelete_enabled_chats:
        ids_to_delete = [message.id]
        if bot_message:
            ids_to_delete.append(bot_message.id)
        asyncio.create_task(schedule_deletion(client, chat_id, ids_to_delete))

# ==========================================================
#  AUTO GREETING SYSTEM (MODIFIED FOR AUTODELETE)
# ==========================================================
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    if not groq_client: return
    try:
        bot_name = client.me.first_name
        use_emojis = should_use_emojis()
        emoji_instruction = "Use appropriate emojis" if use_emojis else "Do not use any emojis"
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_NAME,
            messages=[{"role": "system", "content": f"You are {bot_name}, a cheerful Tanglish friend. Generate a short '{message_type}' message."}, {"role": "user", "content": f"Write a short '{message_type}' greeting in Tanglish slang. {emoji_instruction}. Keep it under 60 characters."}],
            temperature=0.8, max_tokens=60,
        )
        greeting_text = response.choices[0].message.content
        if not use_emojis: greeting_text = remove_emojis(greeting_text)
        fancy_greeting = to_fancy_font(greeting_text)
        
        # --- CHANGE 14: Capture the sent message ---
        bot_message = await client.send_message(chat_id, fancy_greeting)
        
        # --- CHANGE 15: Schedule deletion if autodelete is enabled ---
        if chat_id in autodelete_enabled_chats and bot_message:
            asyncio.create_task(schedule_deletion(client, chat_id, [bot_message.id]))

    except Exception as e: print(f"[AI] Greeting error in {chat_id}: {e}")

async def greeting_scheduler(client: Client):
    global greeting_morning_sent, greeting_night_sent
    while True:
        now = datetime.now().time()
        if now.hour == 0 and now.minute == 0: greeting_morning_sent = greeting_night_sent = False
        if now.hour == 7 and now.minute == 30 and not greeting_morning_sent:
            print("[AI] Sending morning greetings...")
            for gid in ai_enabled_groups: await send_greeting_message(client, gid, "Good morning")
            greeting_morning_sent = True
        elif now.hour == 22 and now.minute == 30 and not greeting_night_sent:
            print("[AI] Sending night greetings...")
            for gid in ai_enabled_groups: await send_greeting_message(client, gid, "Good night")
            greeting_night_sent = True
        await asyncio.sleep(60)

async def start_greeting_task(client: Client):
    print("[AI] Starting greeting scheduler task.")
    asyncio.create_task(greeting_scheduler(client))
