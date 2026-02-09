# plugins/web_support.py
import logging
import random
import aiohttp
from aiohttp import web
from instagrapi import Client as InstaClient

from database.users import db
from config import MONGO_DB_NAME, INSTA_PROXIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ NEW: Auto-Fetch Free Proxies
free_proxy_list = INSTA_PROXIES.copy()

async def fetch_free_proxies():
    """Automatically fetches free proxies from a public API."""
    global free_proxy_list
    logger.info("🌐 Fetching free proxies from public API...")
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
                    logger.info(f"✅ Fetched {len(proxies)} free proxies. Total pool: {len(free_proxy_list)}")
    except Exception as e:
        logger.error(f"❌ Failed to fetch free proxies: {e}")

def get_random_proxy():
    """Picks a random proxy."""
    global free_proxy_list
    if free_proxy_list:
        return f"http://{random.choice(free_proxy_list)}"
    return None

async def check_insta_session_db():
    """Check if Instagram session exists in MongoDB and is valid."""
    logger.info(f"🔍 [Web] Checking for Instagram session in database '{MONGO_DB_NAME}'...")
    session_doc = await db.get_insta_session(MONGO_DB_NAME)
    
    if session_doc and "settings" in session_doc:
        if not free_proxy_list:
            await fetch_free_proxies()

        proxy = get_random_proxy()
        logger.info(f"🌐 [Web] Using proxy: {proxy}")
        
        try:
            temp_client = InstaClient(proxy=proxy)
            temp_client.set_settings(session_doc["settings"])
            user_info = temp_client.user_info(temp_client.user_id)
            logger.info(f"✅ [Web] Instagram session valid: {user_info.username}")
            return True, user_info.username
        except Exception as e:
            logger.error(f"❌ [Web] Invalid session or Proxy failed: {e}")
            return False, None
            
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
        # ✅ RICH: Styled Success Page
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

    # ✅ RICH: Styled Instagram Login Page
    html = """
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Instagram Login</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #fafafa; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .container { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 350px; }
            
            /* Card Style */
            .card { background: white; border: 1px solid #dbdbdb; padding: 40px; margin-bottom: 10px; width: 100%; box-sizing: border-box; text-align: center; }
            
            /* Logo */
            .logo-img { width: 175px; margin-bottom: 30px; }
            
            /* Inputs */
            .input-box { background: #fafafa; border: 1px solid #dbdbdb; border-radius: 3px; color: #262626; font-size: 12px; margin: 0 0 6px; padding: 9px 8px 7px; width: 100%; box-sizing: border-box; }
            .input-box:focus { outline: none; border-color: #a8a8a8; }
            
            /* Button */
            .btn-login { background-color: #0095f6; border: 1px solid transparent; border-radius: 4px; color: #fff; cursor: pointer; font-weight: 600; padding: 5px 9px; text-align: center; text-transform: inherit; text-overflow: ellipsis; width: 100%; margin-top: 10px; font-size: 14px; line-height: 18px; padding: 7px 16px; }
            .btn-login:disabled { opacity: 0.3; cursor: default; }
            
            /* Footer */
            .footer { font-size: 12px; color: #8e8e8e; margin-top: 20px; text-align: center; }
            .secure { margin-top: 15px; font-size: 11px; color: #8e8e8e; display: flex; align-items: center; justify-content: center; gap: 5px; }
            
            /* SVG Icon */
            svg { height: 51px; width: 175px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <!-- Instagram SVG Logo -->
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
                    Credentials are sent securely to your bot.
                </div>
            </div>
            
            <div class="footer">
                TamilBots &copy; 2024
            </div>
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
    
    proxy = get_random_proxy()
    logger.info(f"🌐 [Web] Attempting login via proxy: {proxy}")

    try:
        temp_insta_client = InstaClient(proxy=proxy)
        temp_insta_client.login(username, password)
        
        settings = temp_insta_client.get_settings()
        await db.save_insta_session(MONGO_DB_NAME, settings)
        
        logger.info(f"💾 [Web] Instagram session for '{username}' saved to MongoDB.")
        
        # ✅ RICH: Styled Success Page
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
        logger.error(f"[Web] Login failed: {e}")
        # Simple error page
        html = f"""
        <html>
        <body style="font-family:sans-serif;text-align:center;margin-top:100px">
            <h2 style="color:red">Login Failed</h2>
            <p>{str(e)}</p>
            <p><a href="/insta_login" style="color:#0095f6">Try Again</a></p>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

async def web_server():
    web_app = web.Application(client_max_size=30_000_000)
    web_app.add_routes(routes)
    return web_app
