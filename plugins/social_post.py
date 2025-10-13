# plugins/social_post.py
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from instagrapi import Client as InstaClient
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from config import ADMIN_IDS

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Directories for session storage ---
os.makedirs("sessions", exist_ok=True)
INSTA_SESSION_FILE = "sessions/insta_session.json"
YT_TOKEN_FILE = "sessions/yt_token.json"
YT_CLIENT_SECRETS_FILE = "sessions/yt_client_secret.json"

# --- Global clients ---
insta_client = None
yt_service = None
yt_credentials = None

# --- Helper Functions ---
def check_yt_credentials():
    """Check if YouTube credentials are valid and refresh if needed."""
    global yt_credentials, yt_service
    
    if not os.path.exists(YT_TOKEN_FILE):
        return False
    
    try:
        yt_credentials = Credentials.from_authorized_user_file(YT_TOKEN_FILE)
        # Check if credentials are expired and refresh if possible
        if yt_credentials.expired and yt_credentials.refresh_token:
            yt_credentials.refresh(Request())
            with open(YT_TOKEN_FILE, "w") as token:
                token.write(yt_credentials.to_json())
        
        # Build or rebuild the service
        yt_service = build("youtube", "v3", credentials=yt_credentials)
        return True
    except Exception as e:
        logger.error(f"Error checking YouTube credentials: {e}")
        return False

def check_insta_session():
    """Check if Instagram session is valid."""
    global insta_client
    
    if not os.path.exists(INSTA_SESSION_FILE):
        return False
    
    try:
        insta_client = InstaClient()
        insta_client.load_settings(INSTA_SESSION_FILE)
        # Test if session is still valid
        insta_client.get_timeline_feed()
        return True
    except Exception as e:
        logger.error(f"Error checking Instagram session: {e}")
        return False

# --- 1️⃣ Instagram login ---
@Client.on_message(filters.command("insta_login") & filters.user(ADMIN_IDS))
async def insta_login(client: Client, message: Message):
    global insta_client
    await message.reply("📲 Logging into Instagram...")
    
    try:
        insta_client = InstaClient()
        insta_user = os.getenv("INSTA_USERNAME")
        insta_pass = os.getenv("INSTA_PASSWORD")

        if not insta_user or not insta_pass:
            await message.reply("❌ Instagram credentials not found in environment variables.")
            return

        if os.path.exists(INSTA_SESSION_FILE):
            if check_insta_session():
                await message.reply("✅ Instagram session loaded from file and is valid.")
            else:
                await message.reply("⚠️ Session file exists but is invalid. Creating new session...")
                raise Exception("Invalid session")
        else:
            insta_client.login(insta_user, insta_pass)
            insta_client.dump_settings(INSTA_SESSION_FILE)
            await message.reply("✅ Instagram login successful and session saved.")

    except Exception as e:
        try:
            # Try to login again if session was invalid
            insta_client.login(insta_user, insta_pass)
            insta_client.dump_settings(INSTA_SESSION_FILE)
            await message.reply("✅ Instagram login successful and new session saved.")
        except Exception as retry_e:
            logger.error(f"Instagram login failed: {retry_e}")
            await message.reply(f"❌ Instagram login failed: {retry_e}")

# --- 2️⃣ Instagram post ---
@Client.on_message(filters.command("insta_post") & filters.user(ADMIN_IDS))
async def insta_post(client: Client, message: Message):
    global insta_client
    
    if not check_insta_session():
        await message.reply("⚠️ Please run /insta_login first.")
        return

    # Check if message is a reply with video
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply("❌ Reply to a Telegram video to post on Instagram.")
        return

    caption = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    file = await message.reply_to_message.download()
    await message.reply("📤 Uploading video to Instagram...")

    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            insta_client.video_upload(file, caption=caption, cover=None, reels=True)
            await message.reply("✅ Video posted to Instagram Reels successfully!")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"Instagram upload attempt {retry_count} failed: {e}")
            if retry_count >= max_retries:
                await message.reply(f"❌ Failed to post to Instagram after {max_retries} attempts: {e}")
            else:
                await message.reply(f"⚠️ Upload attempt {retry_count} failed. Retrying...")
                await asyncio.sleep(2)
    finally:
        if os.path.exists(file):
            os.remove(file)

# --- 3️⃣ YouTube login ---
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
@Client.on_message(filters.command("yt_login") & filters.user(ADMIN_IDS))
async def yt_login(client: Client, message: Message):
    global yt_service, yt_credentials
    await message.reply("📲 Initiating YouTube login process...")
    
    try:
        creds_file_content = os.getenv("YT_CLIENT_SECRET")
        if not creds_file_content:
            await message.reply("❌ YouTube client secret not found in environment variables.")
            return
            
        with open(YT_CLIENT_SECRETS_FILE, "w") as f:
            f.write(creds_file_content)

        # Try to use existing token if available
        if check_yt_credentials():
            await message.reply("✅ YouTube credentials loaded from file and are valid.")
            return

        # If no valid credentials, start OAuth flow
        await message.reply("🔗 Please complete the OAuth flow in your browser...")
        
        # Use a more server-friendly approach
        flow = Flow.from_client_secrets_file(YT_CLIENT_SECRETS_FILE, SCOPES)
        flow.redirect_uri = "http://localhost:8080/"
        
        auth_url, _ = flow.authorization_url(prompt='consent')
        await message.reply(f"🌐 Please visit this URL to authorize the application: {auth_url}")
        await message.reply("⏳ After authorizing, you'll be redirected to a page with a code in the URL.")
        await message.reply("📝 Please copy the full URL and send it back to me with /yt_code command.")
        
        # Store the flow for later use in yt_code command
        global yt_flow
        yt_flow = flow
        
    except Exception as e:
        logger.error(f"YouTube login failed: {e}")
        await message.reply(f"❌ YouTube login failed: {e}")

# --- 3️⃣b YouTube code handler ---
@Client.on_message(filters.command("yt_code") & filters.user(ADMIN_IDS))
async def yt_code(client: Client, message: Message):
    global yt_service, yt_credentials, yt_flow
    
    if not yt_flow:
        await message.reply("❌ No pending YouTube authorization. Please start with /yt_login first.")
        return
    
    try:
        # Extract the code from the URL
        if len(message.command) < 2:
            await message.reply("❌ Please provide the authorization code or full URL.")
            return
            
        auth_response = message.command[1]
        if "http" in auth_response:
            # Extract code from URL
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(auth_response)
            code = parse_qs(parsed_url.query).get('code', [None])[0]
            if not code:
                await message.reply("❌ Could not extract authorization code from URL.")
                return
        else:
            code = auth_response
        
        yt_flow.fetch_token(code=code)
        yt_credentials = yt_flow.credentials
        
        with open(YT_TOKEN_FILE, "w") as token:
            token.write(yt_credentials.to_json())
            
        yt_service = build("youtube", "v3", credentials=yt_credentials)
        await message.reply("✅ YouTube login successful and token saved!")
        
        # Clear the flow
        yt_flow = None
        
    except Exception as e:
        logger.error(f"YouTube code verification failed: {e}")
        await message.reply(f"❌ YouTube code verification failed: {e}")

# --- 4️⃣ YouTube post ---
@Client.on_message(filters.command("yt_post") & filters.user(ADMIN_IDS))
async def yt_post(client: Client, message: Message):
    global yt_service
    
    if not check_yt_credentials():
        await message.reply("⚠️ Please run /yt_login first.")
        return

    # Check if message is a reply with video
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply("❌ Reply to a Telegram video to post on YouTube.")
        return

    try:
        # Parse command arguments
        cmd_text = " ".join(message.command[1:])
        title = "Telegram Upload"
        description = ""
        privacy = "private"
        tags = []
        
        # Parse arguments in format: title | description | privacy | tag1,tag2,tag3
        parts = [x.strip() for x in cmd_text.split("|")]
        
        if len(parts) >= 1 and parts[0]:
            title = parts[0]
        if len(parts) >= 2 and parts[1]:
            description = parts[1]
        if len(parts) >= 3 and parts[2]:
            if parts[2].lower() in ["public", "private", "unlisted"]:
                privacy = parts[2].lower()
        if len(parts) >= 4 and parts[3]:
            tags = [tag.strip() for tag in parts[3].split(",")]
        
        file = await message.reply_to_message.download()
        await message.reply(f"📤 Uploading video to YouTube with title: '{title}'...")

        media = MediaFileUpload(file, resumable=True)
        request = yt_service.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title, 
                    "description": description, 
                    "categoryId": "22",
                    "tags": tags
                },
                "status": {"privacyStatus": privacy},
            },
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                await message.reply(f"📊 Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response.get("id", "")
        video_url = f"https://youtu.be/{video_id}"
        await message.reply(f"✅ Video posted to YouTube!\n🔗 URL: {video_url}\n🔒 Privacy: {privacy}")
        
    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        await message.reply(f"❌ Failed to post to YouTube: {e}")
    finally:
        if 'file' in locals() and os.path.exists(file):
            os.remove(file)

# --- 5️⃣ Status command ---
@Client.on_message(filters.command("social_status") & filters.user(ADMIN_IDS))
async def social_status(client: Client, message: Message):
    """Check login status for social media platforms."""
    status_text = "📊 **Social Media Login Status**\n\n"
    
    # Check Instagram
    if check_insta_session():
        status_text += "📷 Instagram: ✅ Logged in\n"
    else:
        status_text += "📷 Instagram: ❌ Not logged in\n"
    
    # Check YouTube
    if check_yt_credentials():
        status_text += "📺 YouTube: ✅ Logged in\n"
    else:
        status_text += "📺 YouTube: ❌ Not logged in\n"
    
    await message.reply(status_text)
