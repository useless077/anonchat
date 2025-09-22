import os

class Config:
    # Telegram Bot
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API_ID = int(os.environ.get("API_ID", "1779071"))   # optional if using BotToken only
    API_HASH = os.environ.get("API_HASH", "3448177952613312689f44b9d909b5d3")

    # Mongo
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://tamilmovie:tamilmovie@cluster0.lxatf.mongodb.net/tamilmovie?retryWrites=true&w=majority")
    DB_NAME = os.environ.get("DB_NAME", "anon_chat")

    # Audit & Admin
    AUDIT_CHAT_ID = int(os.environ.get("AUDIT_CHAT_ID", "-1003058488661"))  # Channel/Group for logs
    ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "7066475210").split(",")))  # comma-separated

    # Matching
    ENABLE_PREF_MATCH = os.environ.get("ENABLE_PREF_MATCH", "false").lower() == "true"

    # Deployment
    PORT = int(os.environ.get("PORT", "8080"))
    WEBHOOK = os.environ.get("WEBHOOK_URL", "favourable-dorita-tamilanbots-e6acad40.koyeb.app/")
