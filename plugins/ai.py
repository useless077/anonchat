# plugins/ai.py

import asyncio
import datetime
import random
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

# --- AI KU PESUM STYLE (PERSONA PROMPT) ---
# Indha prompt AI group la epadi pesanum nu define pannum. Tanglish la pesanum nu command kudukrom.
AI_PERSONA_PROMPT = (
    "You are a friendly, witty, and highly conversational Telegram group member "
    "named 'Gemini'. Your goal is to engage in natural, human-like chat, "
    "keeping conversations flowing and responding to group dynamic. "
    "Do not act like a formal assistant. Keep your replies concise, witty, and relatable. "
    "IMPORTANT: You must always reply in Tanglish, which is a mix of Tamil and English. "
    "For example, 'Enna panra brother?' or 'Super ah irukku da.' "
    "Your responses should feel natural to a Tamil-speaking audience."
)

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

    if not await db.get_ai_status(message.chat.id):
        return

    if message.from_user and message.from_user.is_bot:
        return
        
    if message.text and message.text.startswith('/'):
        return

    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)

    # 1. Message type base panni best prompt ah decide pannrom
    if message.text:
        prompt = f"{AI_PERSONA_PROMPT}\n\nUser Message: {message.text}"
    
    elif message.photo:
        prompt = (
            f"{AI_PERSONA_PROMPT}\n\nUser sent a photo with caption: '{message.caption or ''}'. "
            "Analyze the caption's meaning or the general context implied by sending a photo "
            "and respond conversationally in Tanglish."
        )

    elif message.animation:
        prompt = (
            f"{AI_PERSONA_PROMPT}\n\nUser sent a GIF. Acknowledge the GIF's mood/theme "
            "and respond conversationally in Tanglish, perhaps by referencing a recent topic "
            "or acknowledging the humor."
        )
        
    elif message.sticker:
        prompt = (
            f"{AI_PERSONA_PROMPT}\n\nUser sent a sticker. Analyze the sticker's implied emotion "
            "or meaning and respond conversationally in Tanglish, keeping in mind the ongoing chat context."
        )
        
    elif message.video:
        prompt = (
             f"{AI_PERSONA_PROMPT}\n\nUser sent a video with caption: '{message.caption or ''}'. "
             "Respond conversationally in Tanglish to the video or caption."
        )
        
    else:
        return

    # 2. AI reply ah generate pannrom
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text

        await message.reply(ai_reply)

    except Exception as e:
        print(f"[AI] Reply generate pannumbothu error: {e}")


# --- SCHEDULED GREETING FUNCTIONS ---
# Indha function unga main file la irukka scheduler call pannum.
async def send_greeting_message(client: Client, chat_id: int, message_type: str):
    """Scheduled greeting ah generate panni send pannum."""
    if not model:
        return

    # Short-a irukka Tanglish greeting prompt
    greeting_prompt = (
        f"You are the friendly group member 'Gemini'. Write a brief, cheerful "
        f"'{message_type}' greeting for the group chat. Keep it natural and short. "
        f"IMPORTANT: You must write the greeting in Tanglish (a mix of Tamil and English). "
        f"For example, 'Good morning ponga, super day ah irukum!' or 'Whats up guys, epdi irukkeenga?'"
    )

    try:
        response = model.generate_content(greeting_prompt)
        await client.send_message(chat_id, response.text)
    except Exception as e:
        print(f"[AI] {chat_id} ku scheduled greeting send pannumbothu error: {e}")
