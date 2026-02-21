import random
import string
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId

from core.auth import get_current_user
from core.database import rooms_col
from models.schemas import (
    CreateRoomRequest, JoinRoomRequest, RoomResponse,
    Room, Member, RoomStatus, utcnow,
)

router = APIRouter(prefix="/rooms", tags=["Rooms"])


def _gen_join_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def _unique_join_code() -> str:
    for _ in range(10):
        code = _gen_join_code()
        if not await rooms_col().find_one({"join_code": code}):
            return code
    raise RuntimeError("Could not generate a unique join code — try again")


def _room_to_response(doc: dict) -> RoomResponse:
    return RoomResponse(
        id=str(doc["_id"]),
        language=doc["language"],
        level=doc["level"],
        max_players=doc["max_players"],
        join_code=doc["join_code"],
        status=doc["status"],
        created_by=doc["created_by"],
        created_at=doc["created_at"],
        members=[Member(**m) for m in doc.get("members", [])],
        last_scenario=doc.get("last_scenario"),
        last_scenario_title=doc.get("last_scenario_title"),
        last_conversation_id=doc.get("last_conversation_id"),
    )


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(body: CreateRoomRequest, current_user: dict = Depends(get_current_user)):
    join_code = await _unique_join_code()
    user_id = current_user["sub"]
    username = current_user["username"]

    creator_member = Member(
        user_id=user_id,
        username=username,
        display_name=body.display_name,
        joined_at=utcnow(),
    )

    room = Room(
        language=body.language,
        level=body.level,
        max_players=body.max_players,
        join_code=join_code,
        status=RoomStatus.waiting,
        created_by=user_id,
        members=[creator_member],
    )

    doc = room.model_dump()
    doc["_id"] = ObjectId(room.id)
    await rooms_col().insert_one(doc)

    return _room_to_response(await rooms_col().find_one({"_id": doc["_id"]}))


@router.post("/join", response_model=RoomResponse)
async def join_room(body: JoinRoomRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    username = current_user["username"]

    room_doc = await rooms_col().find_one({"join_code": body.join_code.upper()})
    if not room_doc:
        raise HTTPException(status_code=404, detail="Room not found")

    if room_doc["status"] != RoomStatus.waiting:
        raise HTTPException(status_code=409, detail="Room is no longer accepting players")

    members = room_doc.get("members", [])

    # Already a member?
    if any(m["user_id"] == user_id for m in members):
        raise HTTPException(status_code=409, detail="You are already in this room")

    # Room full?
    if len(members) >= room_doc["max_players"]:
        raise HTTPException(status_code=409, detail="Room is full")

    new_member = Member(
        user_id=user_id,
        username=username,
        display_name=body.display_name,
        joined_at=utcnow(),
    ).model_dump()

    await rooms_col().update_one(
        {"_id": room_doc["_id"]},
        {"$push": {"members": new_member}},
    )

    updated = await rooms_col().find_one({"_id": room_doc["_id"]})
    return _room_to_response(updated)


@router.get("", response_model=list[RoomResponse])
async def list_my_rooms(current_user: dict = Depends(get_current_user)):
    """Return all rooms the current user is a member of, newest first."""
    user_id = current_user["sub"]
    cursor = rooms_col().find(
        {"members.user_id": user_id},
        sort=[("created_at", -1)],
    )
    return [_room_to_response(doc) async for doc in cursor]


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(room_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid room ID")

    doc = await rooms_col().find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Room not found")

    user_id = current_user["sub"]
    if not any(m["user_id"] == user_id for m in doc.get("members", [])):
        raise HTTPException(status_code=403, detail="You are not a member of this room")

    return _room_to_response(doc)
