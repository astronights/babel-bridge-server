# LingoTogether API

AI-powered multiplayer language learning backend built with FastAPI, MongoDB (Motor), and Google Gemini.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Fill in your `.env`:

```
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/lingotogether?retryWrites=true&w=majority
JWT_SECRET=a-long-random-string-at-least-32-chars
JWT_EXPIRE_MINUTES=10080
GOOGLE_API_KEY=your_google_gemini_api_key
```

- **MONGODB_URI** — your MongoDB Atlas connection string
- **JWT_SECRET** — any long random string; used to sign tokens
- **JWT_EXPIRE_MINUTES** — 10080 = 7 days
- **GOOGLE_API_KEY** — from https://aistudio.google.com/app/apikey

### 3. Run

```bash
uvicorn main:app --reload
```

Interactive docs at: http://localhost:8000/docs

---

## API Reference

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register a new user, returns JWT |
| POST | `/auth/login` | Login, returns JWT |

All other endpoints require: `Authorization: Bearer <token>`

---

### Rooms

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rooms` | Create a room |
| POST | `/rooms/join` | Join a room by join code |
| GET | `/rooms` | List all rooms you're a member of |
| GET | `/rooms/{room_id}` | Get a single room |

**Create room body:**
```json
{
  "language": "Russian",
  "level": "B1",
  "max_players": 2,
  "display_name": "Maria"
}
```

**Join room body:**
```json
{
  "join_code": "X7K2AB",
  "display_name": "Kenji"
}
```

---

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rooms/{room_id}/conversations` | Start a new conversation (creator only) |
| GET | `/rooms/{room_id}/conversations` | List conversations in a room |
| GET | `/rooms/{room_id}/conversations/{conv_id}` | Get a conversation |
| POST | `/rooms/{room_id}/conversations/{conv_id}/turns/{turn_number}` | Submit a turn response |

**Start conversation body:**
```json
{
  "prompt": "Two friends argue about which film to watch"
}
```
Leave `prompt` null or empty to use a pre-defined scenario for the language + level.

**Submit turn body:**
```json
{
  "text": "Privet, kak dela?"
}
```

---

## Data Model

### MongoDB Collections

**users**
```json
{
  "_id": "ObjectId",
  "username": "maria",
  "password_hash": "bcrypt hash",
  "created_at": "datetime"
}
```

**rooms**
```json
{
  "_id": "ObjectId",
  "language": "Russian",
  "level": "B1",
  "max_players": 2,
  "join_code": "X7K2AB",
  "status": "waiting | active | completed",
  "created_by": "user_id",
  "created_at": "datetime",
  "members": [
    {
      "user_id": "...",
      "username": "maria",
      "display_name": "Maria",
      "joined_at": "datetime"
    }
  ]
}
```

**conversations**
```json
{
  "_id": "ObjectId",
  "room_id": "...",
  "prompt": "Two friends at a café",
  "status": "active | completed",
  "current_turn": 3,
  "created_at": "datetime",
  "participants": [
    { "user_id": "...", "username": "maria", "display_name": "Maria", "role": "A", "is_ai": false },
    { "role": "B", "is_ai": true }
  ],
  "messages": [
    {
      "turn_number": 1,
      "speaker": "A",
      "roman_text": "Privet! Kak dela?",
      "native_text": "Привет! Как дела?",
      "english_text": "Hi! How are you?",
      "hint": "'Kak dela' literally means 'how are your affairs' — a standard informal greeting.",
      "response": {
        "user_id": "...",
        "display_name": "Maria",
        "text": "Privet, kak dela?",
        "score": 87,
        "score_label": "Great",
        "score_breakdown": "Word match 100% · Similarity 92%",
        "submitted_at": "datetime"
      }
    }
  ]
}
```

---

## Scoring Algorithm

Each submitted response is scored against the `roman_text` of the target message:

- **Word overlap (55%)** — what fraction of target words appear in the response
- **Character similarity (45%)** — 1 − (Levenshtein distance ÷ max length)

Score labels: Perfect (100) · Excellent (90–99) · Great (75–89) · Almost there (55–74) · Partial match (35–54) · Keep practising (0–34)

---

## Turn Logic

- Turns 1–20 are distributed round-robin across roles A/B/C/D.
- When a conversation is started, real members fill roles in join order; unfilled roles are marked `is_ai: true`.
- AI turns are **automatically skipped** — `current_turn` advances past them when a human submits their turn.
- Only the user whose role matches the current turn's `speaker` can submit.
- Once turn 20 is submitted (or the last human turn), the conversation status becomes `completed`.
