from pymongo import AsyncMongoClient
from core.config import settings

_client: AsyncMongoClient | None = None

def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(settings.mongodb_uri)
    return _client


def get_db():
    return get_client()["lingotogether"]


# Shorthand collection accessors
def users_col():
    return get_db()["users"]


def rooms_col():
    return get_db()["rooms"]


def conversations_col():
    return get_db()["conversations"]


async def create_indexes():
    """Run once on startup to ensure indexes exist."""
    await users_col().create_index("username", unique=True)
    await rooms_col().create_index("join_code", unique=True)
    await rooms_col().create_index("members.user_id")
    await conversations_col().create_index("room_id")
