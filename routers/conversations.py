from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId

from core.auth import get_current_user
from core.database import rooms_col, conversations_col
from models.schemas import (
    CreateConversationRequest, InputMode, SubmitResponseRequest, ConversationResponse,
    Conversation, Participant, Response, RoomStatus, ConversationStatus,
    Role, utcnow,
)
from services.ai import generate_conversation
from services.scoring import score_response

router = APIRouter(prefix="/rooms/{room_id}/conversations", tags=["Conversations"])

ROLES = [Role.a, Role.b, Role.c, Role.d]


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_room_or_404(room_id: str) -> dict:
    try:
        oid = ObjectId(room_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid room ID")
    doc = await rooms_col().find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Room not found")
    return doc


async def _get_conversation_or_404(conv_id: str) -> dict:
    try:
        oid = ObjectId(conv_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    doc = await conversations_col().find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return doc


def _assert_member(room_doc: dict, user_id: str) -> dict:
    member = next((m for m in room_doc.get("members", []) if m["user_id"] == user_id), None)
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this room")
    return member


def _conv_to_response(doc: dict) -> ConversationResponse:
    return ConversationResponse(
        id=str(doc["_id"]),
        room_id=doc["room_id"],
        prompt=doc["prompt"],
        status=doc["status"],
        current_turn=doc["current_turn"],
        created_at=doc["created_at"],
        participants=[Participant(**p) for p in doc.get("participants", [])],
        messages=[_msg_from_doc(m) for m in doc.get("messages", [])],
    )


def _msg_from_doc(m: dict):
    from models.schemas import Message, Response as Resp
    resp = None
    if m.get("response"):
        resp = Resp(**m["response"])
    return Message(
        turn_number=m["turn_number"],
        speaker=m["speaker"],
        roman_text=m["roman_text"],
        native_text=m["native_text"],
        english_text=m["english_text"],
        hint=m["hint"],
        response=resp,
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    room_id: str,
    body: CreateConversationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Only the room creator can start a conversation.
    Assigns roles to current members in join order; empty slots become AI turns.
    Calls Gemini to generate all 20 messages.
    """
    user_id = current_user["sub"]
    room_doc = await _get_room_or_404(room_id)
    _assert_member(room_doc, user_id)

    if room_doc["created_by"] != user_id:
        raise HTTPException(status_code=403, detail="Only the room creator can start a conversation")

    if room_doc["status"] == RoomStatus.completed:
        raise HTTPException(status_code=409, detail="Room is completed")

    members = room_doc.get("members", [])
    if not members:
        raise HTTPException(status_code=409, detail="No members in room")

    # Build participants — real members get roles first, then pad with AI
    participants: list[Participant] = []
    for i, role in enumerate(ROLES[: room_doc["max_players"]]):
        if i < len(members):
            m = members[i]
            participants.append(Participant(
                user_id=m["user_id"],
                username=m["username"],
                display_name=m["display_name"],
                role=role,
                is_ai=False,
            ))
        else:
            participants.append(Participant(role=role, is_ai=True))

    # Generate conversation via Gemini
    try:
        scenario, messages = await generate_conversation(
            language=room_doc["language"],
            level=room_doc["level"],
            participants=participants,
            prompt=body.prompt,
            max_turns=body.max_turns,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    conv = Conversation(
        room_id=room_id,
        prompt=scenario,
        participants=participants,
        messages=messages,
        current_turn=1,
    )

    doc = conv.model_dump()
    doc["_id"] = ObjectId(conv.id)

    # Convert nested models to plain dicts for MongoDB
    doc["participants"] = [p.model_dump() for p in participants]
    doc["messages"] = [m.model_dump() for m in messages]

    await conversations_col().insert_one(doc)

    # Mark room as active
    await rooms_col().update_one(
        {"_id": ObjectId(room_id)},
        {"$set": {"status": RoomStatus.active}},
    )

    saved = await conversations_col().find_one({"_id": doc["_id"]})
    return _conv_to_response(saved)


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    room_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all conversations in a room, newest first."""
    room_doc = await _get_room_or_404(room_id)
    _assert_member(room_doc, current_user["sub"])

    cursor = conversations_col().find(
        {"room_id": room_id},
        sort=[("created_at", -1)],
    )
    return [_conv_to_response(doc) async for doc in cursor]


@router.get("/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    room_id: str,
    conv_id: str,
    current_user: dict = Depends(get_current_user),
):
    room_doc = await _get_room_or_404(room_id)
    _assert_member(room_doc, current_user["sub"])

    conv_doc = await _get_conversation_or_404(conv_id)
    if conv_doc["room_id"] != room_id:
        raise HTTPException(status_code=404, detail="Conversation not found in this room")

    return _conv_to_response(conv_doc)


@router.post("/{conv_id}/turns/{turn_number}", response_model=ConversationResponse)
async def submit_turn(
    room_id: str,
    conv_id: str,
    turn_number: int,
    body: SubmitResponseRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Submit a response for a specific turn.
    - Must be the current turn.
    - Must be the user whose role matches the turn's speaker.
    - AI turns are auto-skipped when the conversation is fetched.
    """
    user_id = current_user["sub"]
    room_doc = await _get_room_or_404(room_id)
    _assert_member(room_doc, user_id)

    conv_doc = await _get_conversation_or_404(conv_id)
    if conv_doc["room_id"] != room_id:
        raise HTTPException(status_code=404, detail="Conversation not found in this room")

    if conv_doc["status"] == ConversationStatus.completed:
        raise HTTPException(status_code=409, detail="Conversation is already completed")

    current_turn = conv_doc["current_turn"]
    if turn_number != current_turn:
        raise HTTPException(
            status_code=409,
            detail=f"It is turn {current_turn}, not turn {turn_number}",
        )

    # Find the message for this turn
    messages = conv_doc["messages"]
    msg_index = next((i for i, m in enumerate(messages) if m["turn_number"] == turn_number), None)
    if msg_index is None:
        raise HTTPException(status_code=404, detail="Turn not found")

    msg = messages[msg_index]

    # Verify this user owns the speaker role for this turn
    speaker_role = msg["speaker"]
    participants = conv_doc["participants"]
    participant = next(
        (p for p in participants if p["role"] == speaker_role and not p["is_ai"]),
        None,
    )
    if not participant or participant["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="It is not your turn")

    # Score the response
    target_text = msg["native_text"] if body.input_mode == InputMode.native else msg["roman_text"]
    result = score_response(body.text, target_text)

    response_doc = Response(
        user_id=user_id,
        display_name=participant["display_name"],
        text=body.text,
        input_mode=body.input_mode,
        score=result["score"],
        score_label=result["label"],
        score_breakdown=result["breakdown"],
        submitted_at=utcnow(),
    ).model_dump()

    # Determine next turn (skip AI turns automatically)
    next_turn = _find_next_human_turn(messages, turn_number, participants)
    new_status = ConversationStatus.completed if next_turn is None else ConversationStatus.active
    total_turns = len(messages)
    new_current = next_turn if next_turn else total_turns + 1

    await conversations_col().update_one(
        {"_id": ObjectId(conv_id)},
        {
            "$set": {
                f"messages.{msg_index}.response": response_doc,
                "current_turn": new_current,
                "status": new_status,
            }
        },
    )

    # If conversation completed, mark room as completed too
    if new_status == ConversationStatus.completed:
        await rooms_col().update_one(
            {"_id": ObjectId(room_id)},
            {"$set": {"status": RoomStatus.completed}},
        )

    updated = await conversations_col().find_one({"_id": ObjectId(conv_id)})
    return _conv_to_response(updated)


def _find_next_human_turn(
    messages: list[dict],
    current_turn_number: int,
    participants: list[dict],
) -> int | None:
    """
    Starting from the turn after current_turn_number, find the next turn
    that belongs to a real (non-AI) participant. Returns None if no such turn exists.
    """
    ai_roles = {p["role"] for p in participants if p["is_ai"]}
    remaining = sorted(
        (m for m in messages if m["turn_number"] > current_turn_number),
        key=lambda m: m["turn_number"],
    )
    for m in remaining:
        if m["speaker"] not in ai_roles:
            return m["turn_number"]
    return None
