from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId


# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_object_id() -> str:
    return str(ObjectId())


# ─────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────

class Language(str, Enum):
    russian = "Russian"
    chinese = "Chinese"
    swedish = "Swedish"


class Level(str, Enum):
    a1 = "A1"
    a2 = "A2"
    b1 = "B1"
    b2 = "B2"
    c1 = "C1"
    c2 = "C2"


class RoomStatus(str, Enum):
    waiting = "waiting"
    active = "active"
    completed = "completed"


class ConversationStatus(str, Enum):
    active = "active"
    completed = "completed"


class Role(str, Enum):
    a = "A"
    b = "B"
    c = "C"
    d = "D"


# ─────────────────────────────────────────
#  Sub-documents (embedded)
# ─────────────────────────────────────────

class Member(BaseModel):
    user_id: str
    username: str
    display_name: str
    joined_at: datetime = Field(default_factory=utcnow)


class Participant(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    role: Role
    is_ai: bool = False


class Response(BaseModel):
    user_id: str
    display_name: str
    text: str
    score: int  # 0-100
    score_label: str
    score_breakdown: str
    submitted_at: datetime = Field(default_factory=utcnow)


class Message(BaseModel):
    turn_number: int
    speaker: Role
    roman_text: str        # Romanised / Pinyin / Latin script
    native_text: str       # Original script (Cyrillic, Hanzi, etc.) — same as roman for Swedish
    english_text: str      # English translation
    hint: str              # Grammar / vocab tip
    response: Optional[Response] = None


# ─────────────────────────────────────────
#  Top-level documents
# ─────────────────────────────────────────

class User(BaseModel):
    id: str = Field(default_factory=new_object_id)
    username: str
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class Room(BaseModel):
    id: str = Field(default_factory=new_object_id)
    language: Language
    level: Level
    max_players: int = Field(ge=2, le=4)
    join_code: str
    status: RoomStatus = RoomStatus.waiting
    created_by: str          # user_id
    created_at: datetime = Field(default_factory=utcnow)
    members: list[Member] = []


class Conversation(BaseModel):
    id: str = Field(default_factory=new_object_id)
    room_id: str
    prompt: str
    status: ConversationStatus = ConversationStatus.active
    current_turn: int = 1    # 1-based; 21 means completed
    created_at: datetime = Field(default_factory=utcnow)
    participants: list[Participant] = []
    messages: list[Message] = []


# ─────────────────────────────────────────
#  Request / Response schemas (API surface)
# ─────────────────────────────────────────

# Auth
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# Rooms
class CreateRoomRequest(BaseModel):
    language: Language
    level: Level
    max_players: int = Field(default=2, ge=2, le=4)
    display_name: str = Field(min_length=1, max_length=32)


class JoinRoomRequest(BaseModel):
    join_code: str
    display_name: str = Field(min_length=1, max_length=32)


class RoomResponse(BaseModel):
    id: str
    language: Language
    level: Level
    max_players: int
    join_code: str
    status: RoomStatus
    created_by: str
    created_at: datetime
    members: list[Member]


# Conversations
class CreateConversationRequest(BaseModel):
    prompt: Optional[str] = None   # If blank, AI picks a scenario


class SubmitResponseRequest(BaseModel):
    text: str = Field(min_length=1)


class ConversationResponse(BaseModel):
    id: str
    room_id: str
    prompt: str
    status: ConversationStatus
    current_turn: int
    created_at: datetime
    participants: list[Participant]
    messages: list[Message]
