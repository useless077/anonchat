# plugins/web_support.py
import logging
import random  # <--- Added import
from aiohttp import web
from instagrapi import Client as InstaClient

# --- IMPORT YOUR SHARED DB INSTANCE ---
from database.users import db
from config import MONGO_DB_NAME, INSTA_PROXIES  # <--- Import proxies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_random_proxy():
    """Helper to pick a random proxy."""
    if INSTA_PROXIES:
        return random.choice(INSTA_PROXIES)
    return None

# --- ✅ NEW FUNCTION ---
async def check_insta_session_db():
    """Check if Instagram session exists in MongoDB and is valid using a PROXY."""
    logger.info(f"🔍 [Web] Checking for Instagram session in database '{MONGO_DB_NAME}'...")
    session_doc = await db.get_insta_session(MONGO_DB_NAME)
    
    if session_doc and "settings" in session_doc:
        proxy = get_random_proxy()
        logger.info(f"🌐 [Web] Using proxy: {proxy}")
        
        try:
            # Create a temporary client WITH PROXY to validate the session
            temp_client = InstaClient(proxy=proxy)
            temp_client.set_settings(session_doc["settings"])
            
            # This checks if the session is still valid (it makes a request to IG)
            user_info = temp_client.user_info(temp_client.user_id)
            
            logger.info(f"✅ [Web] Instagram session valid: {user_info.username}")
            return True, user_info.username
        except Exception as e:
            logger.error(f"❌ [Web] Invalid Instagram session in DB: {e}")
            # Clean up the invalid session from DB
            await db.delete_insta_session(MONGO_DB_NAME)
            return False, None
            
    logger.info("ℹ️ [Web] No session found in MongoDB.")
    return False, None

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("TamilBots")

@routes.get("/insta_login")
async def insta_login_page(request):
    """Show login page if session not active."""
    # --- ✅ UPDATED ---
    # Use the new async function to check the database
    is_logged_in, username = await check_insta_session_db()
    
    if is_logged_in:
        return web.Response(
            text=f"✅ Already logged in as {username}! You can close this tab.",
            content_type="text/html"
        )

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

@routes.post("/insta_auth")
async def insta_auth(request):
    """Handle Instagram web login form."""
    data = await request.post()
    username = data.get("username")
    password = data.get("password")
    
    proxy = get_random_proxy()
    logger.info(f"🌐 [Web] Attempting login via proxy: {proxy}")

    try:
        # --- ✅ THE CORE CHANGE ---
        # Create a temporary client WITH PROXY for this login process
        temp_insta_client = InstaClient(proxy=proxy)
        
        # Attempt login
        temp_insta_client.login(username, password)
        
        # After successful login, get the settings and save them to MongoDB
        settings = temp_insta_client.get_settings()
        await db.save_insta_session(MONGO_DB_NAME, settings)
        
        logger.info(f"💾 [Web] Instagram session for '{username}' saved to MongoDB.")
        
        return web.Response(
            text="✅ Instagram login successful! Session saved. You can close this tab.",
            content_type="text/html"
        )
    except Exception as e:
        logger.error(f"[Web] Login failed: {e}")
        return web.Response(text=f"❌ Login failed: {e}", content_type="text/html")

async def web_server():
    """Run aiohttp web server on Koyeb."""
    web_app = web.Application(client_max_size=30_000_000)
    web_app.add_routes(routes)
    return web_app
