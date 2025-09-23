# db.py
import json
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from pyrogram.storage import BaseStorage

# MongoDB client
mongo = AsyncIOMotorClient(Config.MONGO_URI)
db = mongo[Config.DB_NAME]

# Collections for bot data
users = db["users"]
queue = db["queue"]
logs = db["logs"]
sessions = db["sessions"]  # for Pyrogram session storage

# Pyrogram Mongo Storage
class MongoStorage(BaseStorage):
    def __init__(self, collection):
        self.collection = collection

    async def load(self) -> dict:
        doc = await self.collection.find_one({"_id": "session"})
        if doc and "data" in doc:
            return json.loads(doc["data"])
        return {}

    async def save(self, data: dict):
        await self.collection.update_one(
            {"_id": "session"},
            {"$set": {"data": json.dumps(data)}},
            upsert=True
        )

    async def close(self):
        mongo.close()

# Utility to get or create a user
async def get_user(user_id: int):
    user = await users.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "profile": {}, "status": "idle", "partner_id": None}
        await users.insert_one(user)
    return user
