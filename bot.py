from pyrogram import filters
from handlers import handle_start, handle_message, handle_next
from matching import add_user, remove_user

def start_bot(app):
    # /start command
    app.add_handler(filters.command("start"), handle_start)

    # /next command
    app.add_handler(filters.command("next"), handle_next)

    # Message handler
    app.add_handler(filters.text, handle_message)
