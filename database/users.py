import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError, OperationFailure
from config import MONGO_URI, MONGO_DB_NAME

class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        self.ai_settings = self.db["ai_settings"]
        self.autodelete_settings = self.db["autodelete_settings"]

    # ------------------- Connection -------------------
    async def connect(self):
        """Verify MongoDB connection."""
        await self.client.server_info()

    async def close(self):
        """Close MongoDB connection."""
        self.client.close()

    # ------------------- User CRUD -------------------
    async def add_user(self, user_id: int, profile: dict, user_type: str = "user"):
        """
        Add a new user or update an existing one.
        Keeps partner_id and status intact if user exists.
        Stores 'user_type' (default: 'user').
        """
        existing = await self.users.find_one({"_id": user_id})
        if existing:
            # Update profile and optionally user_type
            await self.users.update_one(
                {"_id": user_id},
                {"$set": {"profile": profile, "user_type": user_type}}
            )
        else:
            # Insert new user with all base fields
            await self.users.insert_one({
                "_id": user_id,
                "profile": profile,
                "status": "idle",
                "partner_id": None,
                "user_type": user_type
            })

    async def get_user(self, user_id: int):
        """Return a user document or None if not found."""
        return await self.users.find_one({"_id": user_id})

    async def update_status(self, user_id: int, status: str):
        """Update a user's status (idle/searching/etc)."""
        await self.users.update_one({"_id": user_id}, {"$set": {"status": status}})

    async def set_partner(self, user_id: int, partner_id: int):
        """Set the partner_id for a given user."""
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": partner_id}})

    async def reset_partner(self, user_id: int):
        """Reset partner for a single user."""
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": None}})

    async def reset_partners(self, user1: int, user2: int):
        """Reset partners for both users."""
        await self.reset_partner(user1)
        await self.reset_partner(user2)

    async def set_partners_atomic(self, user1: int, user2: int):
        """
        Set partners for two users atomically using MongoDB transaction with retry logic.
        Ensures consistency even if one update fails.
        """
        max_retries = 3
        for attempt in range(max_retries):
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    try:
                        await self.users.update_one(
                            {"_id": user1},
                            {"$set": {"partner_id": user2}},
                            session=session
                        )
                        await self.users.update_one(
                            {"_id": user2},
                            {"$set": {"partner_id": user1}},
                            session=session
                        )
                        return  # success
                    except OperationFailure as e:
                        if e.has_error_label("TransientTransactionError"):
                            print(f"DB Write Conflict (attempt {attempt + 1}/{max_retries}). Retrying...")
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        else:
                            print(f"Failed to set partners atomically: {e}")
                            raise
        print(f"Failed to set partners after {max_retries} attempts.")
        raise OperationFailure("Could not complete partner pairing after multiple retries.")

    # ------------------- Group Settings (AI) -------------------
    async def get_ai_status(self, chat_id: int) -> bool:
        """Check if AI is enabled for a specific group."""
        settings = await self.ai_settings.find_one({"_id": chat_id})
        return settings.get("ai_enabled", False) if settings else False

    async def set_ai_status(self, chat_id: int, status: bool):
        """Enable or disable AI for a specific group."""
        await self.ai_settings.update_one(
            {"_id": chat_id},
            {"$set": {"ai_enabled": status}},
            upsert=True
        )

    # ------------------- Group Settings (Autodelete) -------------------
    async def get_autodelete_status(self, chat_id: int) -> bool:
        """Check if autodelete is enabled for a specific group."""
        settings = await self.autodelete_settings.find_one({"_id": chat_id})
        return settings.get("autodelete_enabled", False) if settings else False

    async def set_autodelete_status(self, chat_id: int, status: bool):
        """Enable or disable autodelete for a specific group."""
        await self.autodelete_settings.update_one(
            {"_id": chat_id},
            {"$set": {"autodelete_enabled": status}},
            upsert=True
        )

    async def get_all_autodelete_enabled_chats(self) -> set:
        """Get all chat IDs where autodelete is enabled."""
        cursor = self.autodelete_settings.find({"autodelete_enabled": True})
        enabled_chats = set()
        async for document in cursor:
            enabled_chats.add(document["_id"])
        return enabled_chats


# ------------------- Shared instance -------------------
db = Database(MONGO_URI, MONGO_DB_NAME)
