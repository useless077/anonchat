# plugins/social_post.py
import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from instagrapi import Client as InstaClient
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import ADMIN_IDS

# --- Directories for session storage ---
os.makedirs("sessions", exist_ok=True)
INSTA_SESSION_FILE = "sessions/insta_session.json"
YT_TOKEN_FILE = "sessions/yt_token.json"

# --- Global clients ---
insta_client = None
yt_service = None

# --- 1️⃣ Instagram login ---
@Client.on_message(filters.command("insta_login") & filters.user(ADMIN_IDS))
async def insta_login(client: Client, message: Message):
    global insta_client
    await message.reply("📲 Logging into Instagram...")
    try:
        insta_client = InstaClient()
        insta_user = os.getenv("INSTA_USERNAME")
        insta_pass = os.getenv("INSTA_PASSWORD")

        if os.path.exists(INSTA_SESSION_FILE):
            insta_client.load_settings(INSTA_SESSION_FILE)
            await message.reply("✅ Instagram session loaded from file.")
        else:
            insta_client.login(insta_user, insta_pass)
            insta_client.dump_settings(INSTA_SESSION_FILE)
            await message.reply("✅ Instagram login successful and session saved.")

    except Exception as e:
        await message.reply(f"❌ Instagram login failed: {e}")

# --- 2️⃣ Instagram post ---
@Client.on_message(filters.command("insta_post") & filters.user(ADMIN_IDS))
async def insta_post(client: Client, message: Message):
    global insta_client
    if not insta_client:
        await message.reply("⚠️ Please run /insta_login first.")
        return

    # Check if message is a reply with video
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply("❌ Reply to a Telegram video to post on Instagram.")
        return

    caption = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    file = await message.reply_to_message.download()
    await message.reply("📤 Uploading video to Instagram...")

    try:
        insta_client.video_upload(file, caption=caption, cover=None, reels=True)
        await message.reply("✅ Video posted to Instagram Reels successfully!")
    except Exception as e:
        await message.reply(f"❌ Failed to post to Instagram: {e}")
    finally:
        os.remove(file)

# --- 3️⃣ YouTube login ---
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
@Client.on_message(filters.command("yt_login") & filters.user(ADMIN_IDS))
async def yt_login(client: Client, message: Message):
    global yt_service
    await message.reply("📲 Logging into YouTube...")
    try:
        creds_file = os.getenv("YT_CLIENT_SECRET")  # JSON content of client_secret
        with open("sessions/yt_client_secret.json", "w") as f:
            f.write(creds_file)

        flow = InstalledAppFlow.from_client_secrets_file("sessions/yt_client_secret.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open(YT_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

        yt_service = build("youtube", "v3", credentials=creds)
        await message.reply("✅ YouTube login successful and token saved!")

    except Exception as e:
        await message.reply(f"❌ YouTube login failed: {e}")

# --- 4️⃣ YouTube post ---
@Client.on_message(filters.command("yt_post") & filters.user(ADMIN_IDS))
async def yt_post(client: Client, message: Message):
    global yt_service
    if not yt_service:
        await message.reply("⚠️ Please run /yt_login first.")
        return

    # Check if message is a reply with video
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply("❌ Reply to a Telegram video to post on YouTube.")
        return

    try:
        # Parse title | description
        cmd_text = " ".join(message.command[1:])
        if "|" in cmd_text:
            title, description = [x.strip() for x in cmd_text.split("|", 1)]
        else:
            title = cmd_text.strip() or "Telegram Upload"
            description = ""

        file = await message.reply_to_message.download()
        await message.reply("📤 Uploading video to YouTube...")

        media = MediaFileUpload(file)
        request = yt_service.videos().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": description, "categoryId": "22"},
                "status": {"privacyStatus": "private"},
            },
            media_body=media
        )
        response = request.execute()
        await message.reply(f"✅ Video posted to YouTube! ID: {response['id']}")
    except Exception as e:
        await message.reply(f"❌ Failed to post to YouTube: {e}")
    finally:
        if 'file' in locals() and os.path.exists(file):
            os.remove(file)
