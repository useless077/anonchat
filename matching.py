from db import users, queue
from datetime import datetime
from config import Config

async def enqueue(user_id: int, prefs: dict = None):
    await queue.insert_one({
        "user_id": user_id,
        "ts": datetime.utcnow(),
        "prefs": prefs or {}
    })
    await users.update_one({"_id": user_id}, {"$set": {"status": "queued"}})

async def dequeue_pair():
    # simple FIFO
    first = await queue.find_one(sort=[("ts", 1)])
    if not first:
        return None
    await queue.delete_one({"_id": first["_id"]})

    partner = await queue.find_one(sort=[("ts", 1)])
    if not partner:
        await queue.insert_one(first)  # put back
        return None
    await queue.delete_one({"_id": partner["_id"]})

    u1, u2 = first["user_id"], partner["user_id"]
    await users.update_one({"_id": u1}, {"$set": {"status": "paired", "partner_id": u2}})
    await users.update_one({"_id": u2}, {"$set": {"status": "paired", "partner_id": u1}})
    return (u1, u2)
