from pyrogram import filters
from handlers import handle_start, handle_message
from matching import add_user, get_partner

def start_bot(app):
    # /start command
    app.add_handler(filters.command("start"), handle_start)

    # Message handler
    app.add_handler(filters.text, handle_message)
