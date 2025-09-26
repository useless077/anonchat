# config.py
from os import getenv
from dotenv import load_dotenv
import logging

# Load environment variables from a .env file
load_dotenv()

# Set up logging with a specific format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_env_variable(var_name, default=None):
    """Retrieve an environment variable or raise an error if not found."""
    value = getenv(var_name, default)
    if value is None:
        logging.error(f"{var_name} is not set")
        raise ValueError(f"{var_name} is not set")
    return value

# Telegram Bot
BOT_TOKEN = get_env_variable('BOT_TOKEN')
API_ID = int(get_env_variable('API_ID', '1779071'))
if API_ID <= 0:
    logging.error("API_ID must be a positive integer")
    raise ValueError("API_ID must be a positive integer")
API_HASH = get_env_variable('API_HASH', '3448177952613312689f44b9d909b5d3')

# MongoDB
MONGO_URI = get_env_variable(
    'MONGO_URI',
    'mongodb+srv://tamilmovie:tamilmovie@cluster0.lxatf.mongodb.net/tamilmovie?retryWrites=true&w=majority'
)
MONGO_DB_NAME = get_env_variable('MONGO_DB_NAME', 'anon_chat')

# Admin & Logging
LOG_CHANNEL = int(get_env_variable('LOG_CHANNEL', '-1003058488661'))
if LOG_CHANNEL == 0:
    logging.error("LOG_CHANNEL is not set")
    raise ValueError("LOG_CHANNEL is not set")
ADMIN_IDS = list(map(int, get_env_variable('ADMIN_IDS', '7066475210').split(",")))

# Matching feature
ENABLE_PREF_MATCH = get_env_variable('ENABLE_PREF_MATCH', 'false').lower() == "true"

# Deployment
PORT = int(get_env_variable('PORT', '8000'))
if PORT <= 0:
    logging.error("PORT must be a positive integer")
    raise ValueError("PORT must be a positive integer")

WEBHOOK = get_env_variable('WEBHOOK_URL', 'https://anonchattamil.koyeb.app/')
