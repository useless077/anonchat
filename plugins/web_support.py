# Don't Remove Credit @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

import os
from aiohttp import web
from instagrapi import Client as InstaClient
import logging

# --- Setup logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Instagram setup ---
insta_client = InstaClient()
INSTA_SESSION_FILE = "sessions/insta_session.json"
os.makedirs("sessions", exist_ok=True)

# --------------------------------------
# ✅ Check Instagram session
# --------------------------------------
def check_insta_session():
    if not os.path.exists(INSTA_SESSION_FILE):
        return False
    try:
        insta_client.load_settings(INSTA_SESSION_FILE)
        user_info = insta_client.user_info(insta_client.user_id)
        logger.info(f"✅ Instagram session valid: {user_info.username}")
        return True
    except Exception as e:
        logger.error(f"❌ Invalid Instagram session: {e}")
        return False


# --------------------------------------
# 🌐 Web Routes
# --------------------------------------
routes = web.RouteTableDef()


@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("TamilBots")


# 🧠 Instagram Login Page
@routes.get("/insta_login")
async def insta_login_page(request):
    html = """
    <html>
    <body style="font-family:sans-serif;text-align:center;margin-top:100px">
        <h2>Instagram Login</h2>
        <form action="/insta_auth" method="post">
            <input name="username" placeholder="Instagram Username" required><br><br>
            <input type="password" name="password" placeholder="Instagram Password" required><br><br>
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


# 🧠 Handle login form
@routes.post("/insta_auth")
async def insta_auth(request):
    data = await request.post()
    username = data.get("username")
    password = data.get("password")
    try:
        insta_client.login(username, password)
        insta_client.dump_settings(INSTA_SESSION_FILE)
        return web.Response(text="✅ Instagram login successful! You can close this tab.")
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return web.Response(text=f"❌ Login failed: {e}")


# --------------------------------------
# 🚀 aiohttp Web Server
# --------------------------------------
async def web_server():
    web_app = web.Application(client_max_size=30_000_000)
    web_app.add_routes(routes)
    return web_app
