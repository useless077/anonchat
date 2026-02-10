# plugins/web_support.py
import logging
import random
import aiohttp
import asyncio  # Added for async/thread handling
from aiohttp import web
from instagrapi import Client as InstaClient
from instagrapi.exceptions import ChallengeRequired, LoginRequired, TwoFactorRequired

from database.users import db
from config import MONGO_DB_NAME, INSTA_PROXIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- GLOBAL PROXY POOL ---
# Initialize with your config proxies
free_proxy_list = INSTA_PROXIES.copy()

async def fetch_free_proxies():
    """Automatically fetches free proxies from a public API."""
    global free_proxy_list
    logger.info("🌐 Fetching fresh proxies from public API...")
    url = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&simplified=true"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = [p.strip() for p in text.split('\n') if p.strip()]
                    for p in proxies:
                        if p not in free_proxy_list:
                            free_proxy_list.append(p)
                    logger.info(f"✅ Added {len(proxies)} new proxies. Total pool: {len(free_proxy_list)}")
    except Exception as e:
        logger.error(f"❌ Failed to fetch proxies: {e}")

def get_random_proxy():
    """Picks a random proxy from the pool."""
    global free_proxy_list
    if free_proxy_list:
        return random.choice(free_proxy_list)
    return None

async def check_insta_session_db():
    """
    Check if Instagram session exists in MongoDB.
    Note: We just check if the key exists here to avoid proxy errors on page load.
    """
    logger.info(f"🔍 [Web] Checking for Instagram session in database '{MONGO_DB_NAME}'...")
    session_doc = await db.get_insta_session(MONGO_DB_NAME)
    
    if session_doc and "settings" in session_doc:
        # Try to get username safely if possible, otherwise just generic
        try:
            # We create a temp client just to read the username from settings if stored
            temp_client = InstaClient()
            temp_client.set_settings(session_doc["settings"])
            username = getattr(temp_client, 'username', 'User')
            logger.info(f"✅ [Web] Session found for: {username}")
            return True, username
        except:
            return True, "User"
            
    logger.info("ℹ️ [Web] No session found in MongoDB.")
    return False, None

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("TamilBots")

@routes.get("/insta_login")
async def insta_login_page(request):
    is_logged_in, username = await check_insta_session_db()
    
    if is_logged_in:
        html = """
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Logged In</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #fafafa; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .card { background: white; border: 1px solid #dbdbdb; padding: 40px; width: 300px; text-align: center; border-radius: 1px; }
                .logo { font-size: 40px; color: #0095f6; margin-bottom: 20px; }
                h1 { font-size: 18px; font-weight: 600; margin-bottom: 10px; color: #262626; }
                p { font-size: 14px; color: #8e8e8e; }
                .btn { background-color: #0095f6; color: white; border: none; padding: 7px 16px; border-radius: 4px; font-weight: 600; font-size: 14px; cursor: pointer; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="logo">✓</div>
                <h1>Already Logged In</h1>
                <p>You are connected as <strong>@{username}</strong>.</p>
                <p>You can close this tab.</p>
            </div>
        </body>
        </html>
        """.format(username=username)
        return web.Response(text=html, content_type="text/html")

    html = """
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Instagram Login</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #fafafa; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .container { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 350px; }
            .card { background: white; border: 1px solid #dbdbdb; padding: 40px; margin-bottom: 10px; width: 100%; box-sizing: border-box; text-align: center; }
            .logo-img { width: 175px; margin-bottom: 30px; }
            .input-box { background: #fafafa; border: 1px solid #dbdbdb; border-radius: 3px; color: #262626; font-size: 12px; margin: 0 0 6px; padding: 9px 8px 7px; width: 100%; box-sizing: border-box; }
            .input-box:focus { outline: none; border-color: #a8a8a8; }
            .btn-login { background-color: #0095f6; border: 1px solid transparent; border-radius: 4px; color: #fff; cursor: pointer; font-weight: 600; padding: 5px 9px; text-align: center; text-transform: inherit; text-overflow: ellipsis; width: 100%; margin-top: 10px; font-size: 14px; line-height: 18px; padding: 7px 16px; }
            .btn-login:disabled { opacity: 0.3; cursor: default; }
            .footer { font-size: 12px; color: #8e8e8e; margin-top: 20px; text-align: center; }
            .secure { margin-top: 15px; font-size: 11px; color: #8e8e8e; display: flex; align-items: center; justify-content: center; gap: 5px; }
            svg { height: 51px; width: 175px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <svg aria-label="Instagram" viewBox="0 0 103 29" role="img">
                    <path d="M49.5 21.7c-1.8 0-3.3-1.5-3.3-3.3s1.5-3.3 3.3-3.3 3.3 1.5 3.3 3.3-1.5 3.3-3.3 3.3zm0-5.5c-1.2 0-2.2 1-2.2 2.2s1 2.2 2.2 2.2 2.2-1 2.2-2.2-1-2.2-2.2-2.2zm-18.2 5.5c-1.8 0-3.3-1.5-3.3-3.3s1.5-3.3 3.3-3.3 3.3 1.5 3.3 3.3-1.5 3.3-3.3 3.3zm0-5.5c-1.2 0-2.2 1-2.2 2.2s1 2.2 2.2 2.2 2.2-1 2.2-2.2-1-2.2-2.2-2.2zM74.5 21.7c-1.8 0-3.3-1.5-3.3-3.3s1.5-3.3 3.3-3.3 3.3 1.5 3.3 3.3-1.5 3.3-3.3 3.3zm0-5.5c-1.2 0-2.2 1-2.2 2.2s1 2.2 2.2 2.2 2.2-1 2.2-2.2-1-2.2-2.2-2.2z" fill="#262626"></path>
                    <path d="M81.3 15.1c0 3.7-3 6.6-6.8 6.6-3.7 0-6.8-3-6.8-6.6 0-3.7 3-6.6 6.8-6.6 3.7 0 6.8 3 6.8 6.6zm-1.1 0c0-3.1-2.5-5.5-5.7-5.5-3.1 0-5.7 2.5-5.7 5.5 0 3.1 2.5 5.5 5.7 5.5 3.1 0 5.7-2.5 5.7-5.5z" fill="#262626"></path>
                    <path d="M25.5 15.1c0 3.7-3 6.6-6.8 6.6-3.7 0-6.8-3-6.8-6.6 0-3.7 3-6.6 6.8-6.6 3.7 0 6.8 3 6.8 6.6zm-1.1 0c0-3.1-2.5-5.5-5.7-5.5-3.1 0-5.7 2.5-5.7 5.5 0 3.1 2.5 5.5 5.7 5.5 3.1 0 5.7-2.5 5.7-5.5z" fill="#262626"></path>
                    <path d="M2 9.3v11.4h11.4V9.3H2zm1.1 10.3V10.4h9.2v9.2H3.1z" fill="#262626"></path>
                </svg>
                <form action="/insta_auth" method="post">
                    <input name="username" class="input-box" placeholder="Phone number, username, or email" required><br>
                    <input type="password" name="password" class="input-box" placeholder="Password" required><br>
                    <button type="submit" class="btn-login">Log in</button>
                </form>
                <div class="secure">
                    <svg aria-label="Lock" fill="#8e8e8e" height="12" viewBox="0 0 12 12" width="12">
                        <path d="M9 6V5a3 3 0 0 0-6 0v1H1v6h11V6H9zm-5-1a2 2 0 1 1 4 0v1H4V5zm6 6H2V7h8v4z" fill-rule="evenodd"></path>
                    </svg>
                    Credentials are sent securely.
                </div>
            </div>
            <div class="footer">TamilBots &copy; 2024</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

@routes.post("/insta_auth")
async def insta_auth(request):
    data = await request.post()
    username = data.get("username")
    password = data.get("password")
    
    if not free_proxy_list:
        await fetch_free_proxies()
    
    # --- SMART RETRY LOGIC ---
    max_retries = 5
    last_error = None
    
    for attempt in range(max_retries):
        proxy = get_random_proxy()
        logger.info(f"🔄 [Login] Attempt {attempt + 1}/{max_retries} using Proxy: {proxy}")
        
        try:
            # Use asyncio.to_thread so the blocking login doesn't freeze the web server
            temp_insta_client = InstaClient(proxy=proxy)
            await asyncio.to_thread(temp_insta_client.login, username, password)
            
            # SUCCESS
            settings = temp_insta_client.get_settings()
            await db.save_insta_session(MONGO_DB_NAME, settings)
            
            logger.info(f"💾 [Login] Session for '{username}' saved to DB.")
            
            html = """
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Login Success</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #fafafa; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                    .card { background: white; border: 1px solid #dbdbdb; padding: 40px; width: 300px; text-align: center; border-radius: 1px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
                    .checkmark { color: #00c853; font-size: 50px; margin-bottom: 15px; }
                    h2 { font-size: 20px; margin-bottom: 10px; color: #262626; }
                    p { color: #8e8e8e; font-size: 14px; line-height: 1.5; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="checkmark">✓</div>
                    <h2>Login Successful!</h2>
                    <p>Your session has been saved securely.</p>
                    <p>You can close this tab and start posting.</p>
                </div>
            </body>
            </html>
            """
            return web.Response(text=html, content_type="text/html")
            
        except Exception as e:
            last_error = e
            logger.warning(f"⚠️ [Login] Proxy {proxy} failed: {e}")
            
            # If it's a credential error, don't waste time trying other proxies
            err_str = str(e).lower()
            if "challenge" in err_str or "incorrect password" in err_str or "two-factor" in err_str or "sms" in err_str:
                logger.error("❌ [Login] Credentials or 2FA issue. Stopping retries.")
                break # Break the loop
    
    # --- FAILED ALL ATTEMPTS ---
    logger.error(f"❌ [Login] All {max_retries} attempts failed.")
    html = f"""
    <html>
    <body style="font-family:sans-serif;text-align:center;margin-top:100px">
        <h2 style="color:red">Login Failed</h2>
        <p>Tried {max_retries} different proxies, but none worked or credentials are wrong.</p>
        <p>Error: {str(last_error)[:100]}...</p>
        <p><a href="/insta_login" style="color:#0095f6">Try Again</a></p>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

async def web_server():
    web_app = web.Application(client_max_size=30_000_000)
    web_app.add_routes(routes)
    return web_app
