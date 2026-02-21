from fastapi import APIRouter, HTTPException, status
import bcrypt
from bson import ObjectId

from core.database import users_col
from core.auth import create_token
from models.schemas import RegisterRequest, LoginRequest, TokenResponse, User, utcnow

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    # Check username is not taken
    existing = await users_col().find_one({"username": body.username.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = User(
        username=body.username.lower(),
        password_hash=pw_hash,
        created_at=utcnow(),
    )

    doc = user.model_dump()
    doc["_id"] = ObjectId(user.id)
    await users_col().insert_one(doc)

    token = create_token(user.id, user.username)
    return TokenResponse(access_token=token, username=user.username)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await users_col().find_one({"username": body.username.lower()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(str(user["_id"]), user["username"])
    return TokenResponse(access_token=token, username=user["username"])
