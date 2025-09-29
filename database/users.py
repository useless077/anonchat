from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from config import MONGO_URI, MONGO_DB_NAME
class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        
    async def connect(self):
        await self.client.server_info()
        
    async def close(self):
        self.client.close()
        
    async def add_user(self, user_id: int, profile: dict):
        existing = await self.users.find_one({"_id": user_id})
        if existing:
            # Update profile only, keep partner_id and status intact
            await self.users.update_one(
                {"_id": user_id},
                {"$set": {"profile": profile}}
            )
        else:
            # New user
            await self.users.insert_one({
                "_id": user_id,
                "profile": profile,
                "status": "idle",
                "partner_id": None
            })    
            
    async def get_user(self, user_id: int):
        user = await self.users.find_one({"_id": user_id})
        if not user:
            return {"_id": user_id, "profile": {}, "status": "idle", "partner_id": None}
        return user
        
    async def update_status(self, user_id: int, status: str):
        await self.users.update_one({"_id": user_id}, {"$set": {"status": status}})
        
    async def set_partner(self, user_id: int, partner_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": partner_id}})
        
    async def reset_partner(self, user_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": None}})
        
    async def set_partners_atomic(self, user1: int, user2: int):
        session = await self.client.start_session()
        async with session.start_transaction():
            try:
                await self.users.update_one({"_id": user1}, {"$set": {"partner_id": user2}}, session=session)
                await self.users.update_one({"_id": user2}, {"$set": {"partner_id": user1}}, session=session)
            except PyMongoError as e:
                print(f"Failed to set partners atomically: {e}")
                raise


# Shared instance
db = Database(MONGO_URI, MONGO_DB_NAME)
