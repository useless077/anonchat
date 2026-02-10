# database/users.py
import asyncio
from typing import Optional, Dict, Any, List, Set
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from config import MONGO_URI, MONGO_DB_NAME

class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        self.ai_settings = self.db["ai_settings"]
        self.autodelete_settings = self.db["autodelete_settings"]
        # --- NEW ---
        self.insta_sessions = self.db["insta_sessions"]
        self.forwarder_checkpoint = self.db["forwarder_checkpoints"]

    # ------------------- Connection -------------------
    async def connect(self):
        """Verify MongoDB connection."""
        await self.client.server_info()

    async def close(self):
        """Close MongoDB connection."""
        self.client.close()

    # ------------------- User CRUD -------------------
    async def add_user(self, user_id: int, profile: Optional[dict] = None, user_type: str = "user"):
        """
        Add a new user or update existing profile.
        Keeps partner_id and status intact if user exists.
        Stores 'user_type' (default: 'user').
        """
        existing = await self.users.find_one({"_id": user_id})
        if existing:
            update_fields = {}
            if profile is not None:
                update_fields["profile"] = profile
            if user_type is not None:
                update_fields["user_type"] = user_type
            if update_fields:
                await self.users.update_one({"_id": user_id}, {"$set": update_fields})
        else:
            await self.users.insert_one({
                "_id": user_id,
                "profile": profile or {},
                "status": "idle",
                "partner_id": None,
                "user_type": user_type
            })

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Return the user document or None."""
        return await self.users.find_one({"_id": user_id})

    async def get_all_users(self) -> List[int]:
        """Return list of all user IDs."""
        cursor = self.users.find({}, {"_id": 1})
        return [doc["_id"] async for doc in cursor]

    async def remove_user(self, user_id: int):
        """Remove a user (used if they block the bot)."""
        await self.users.delete_one({"_id": user_id})

    async def get_total_users(self) -> int:
        """Return total number of users."""
        return await self.users.count_documents({})

    # ------------------- Status -------------------
    async def update_status(self, user_id: int, status: str):
        """Update user's status (idle/searching/chatting)."""
        await self.users.update_one({"_id": user_id}, {"$set": {"status": status}}, upsert=True)

    # ------------------- Partners -------------------
    async def set_partner(self, user_id: int, partner_id: int):
        """Set partner_id for a single user (non-atomic)."""
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": partner_id}}, upsert=True)

    async def reset_partner(self, user_id: int):
        """Reset partner for a single user."""
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": None}})

    async def reset_partners(self, user1: int, user2: int):
        """Reset partners for both users."""
        await asyncio.gather(
            self.reset_partner(user1),
            self.reset_partner(user2)
        )

    async def set_partners_atomic(self, user1: int, user2: int):
        """
        Set partners for two users atomically using a MongoDB transaction with retry logic.
        Returns on success; raises OperationFailure on persistent failures.
        """
        max_retries = 3
        for attempt in range(max_retries):
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    try:
                        await self.users.update_one(
                            {"_id": user1},
                            {"$set": {"partner_id": user2}},
                            session=session,
                            upsert=True
                        )
                        await self.users.update_one(
                            {"_id": user2},
                            {"$set": {"partner_id": user1}},
                            session=session,
                            upsert=True
                        )
                        return
                    except OperationFailure as e:
                        if e.has_error_label("TransientTransactionError"):
                            # transient, retry
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        else:
                            raise
        raise OperationFailure("Could not complete partner pairing after multiple retries.")

    # ------------------- Counts & Stats -------------------
    async def get_active_chats(self) -> int:
        """
        Returns number of active chat *pairs*.
        Counts users with non-null partner_id and divides by 2 to get pairs.
        """
        active_users = await self.users.count_documents({"partner_id": {"$ne": None}})
        return active_users // 2

    # ------------------- AI Settings -------------------
    async def get_ai_status(self, chat_id: int) -> bool:
        settings = await self.ai_settings.find_one({"_id": chat_id})
        return bool(settings and settings.get("ai_enabled", False))

    async def set_ai_status(self, chat_id: int, status: bool):
        await self.ai_settings.update_one(
            {"_id": chat_id},
            {"$set": {"ai_enabled": status}},
            upsert=True
        )

    async def get_all_ai_enabled_chats(self) -> Set[int]:
        cursor = self.ai_settings.find({"ai_enabled": True})
        return {doc["_id"] async for doc in cursor}

    async def get_total_groups(self) -> int:
        """Return count of group entries in ai_settings (approx. total groups tracked)."""
        return await self.ai_settings.count_documents({})

    # ------------------- Autodelete Settings -------------------
    async def get_autodelete_status(self, chat_id: int) -> bool:
        settings = await self.autodelete_settings.find_one({"_id": chat_id})
        return bool(settings and settings.get("autodelete_enabled", False))

    async def set_autodelete_status(self, chat_id: int, status: bool):
        await self.autodelete_settings.update_one(
            {"_id": chat_id},
            {"$set": {"autodelete_enabled": status}},
            upsert=True
        )

    async def get_all_autodelete_enabled_chats(self) -> Set[int]:
        cursor = self.autodelete_settings.find({"autodelete_enabled": True})
        return {doc["_id"] async for doc in cursor}

    # ------------------- Instagram Session Management (NEW) -------------------
    async def get_insta_session(self, bot_session_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve Instagram session settings for a specific bot."""
        return await self.insta_sessions.find_one({"_id": bot_session_name})

    async def save_insta_session(self, bot_session_name: str, settings: dict):
        """Save or update Instagram session settings for a specific bot."""
        await self.insta_sessions.update_one(
            {"_id": bot_session_name},
            {"$set": {"settings": settings}},
            upsert=True
        )

    async def delete_insta_session(self, bot_session_name: str):
        """Delete the Instagram session for a specific bot."""
        await self.insta_sessions.delete_one({"_id": bot_session_name})

    # --- ADD THESE METHODS INSIDE YOUR CLASS ---
    
    async def get_forwarder_checkpoint(self, source_id):
        """Get the last message ID processed for a source channel."""
        doc = await self.forwarder_checkpoint.find_one({"source_id": source_id})
        if doc:
            return doc.get("last_id", 0)
        return 0

    async def save_forwarder_checkpoint(self, source_id, message_id):
        """Update the last processed message ID."""
        await self.forwarder_checkpoint.update_one(
            {"source_id": source_id},
            {"$set": {"last_id": message_id}},
            upsert=True
        )


# ------------------- Shared instance -------------------
db = Database(MONGO_URI, MONGO_DB_NAME)
