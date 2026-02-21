"""
AI service — generates conversations using Google Gemini.
Language and level data is fetched from MongoDB.
Prompt template is loaded from prompts/conversation.txt.
"""

import json
import re
from pathlib import Path
from typing import Optional
import google.generativeai as genai
from core.config import settings
from core.database import languages_col, levels_col
from models.schemas import Participant, Message, Role

genai.configure(api_key=settings.google_api_key)

# Load prompt template once at import time
PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "conversation.txt").read_text()


async def _get_language(code: str) -> dict:
    lang = await languages_col().find_one({"code": code})
    if not lang:
        raise ValueError(f"Language '{code}' not found in database")
    return lang


async def _get_level(code: str) -> dict:
    level = await levels_col().find_one({"code": code})
    if not level:
        raise ValueError(f"Level '{code}' not found in database")
    return level


def _resolve_scenario(level_doc: dict, lang_code: str, prompt: Optional[str]) -> str:
    if prompt and prompt.strip():
        return prompt.strip()
    # Try language-specific scenario first, fall back to default
    return level_doc.get("scenarios", {}).get(lang_code) or level_doc["default_scenario"]


def _build_prompt(
    lang_doc: dict,
    level_doc: dict,
    scenario: str,
    participants: list[Participant],
    max_turns: int,
) -> str:
    # Describe each role
    role_lines = []
    for p in participants:
        if p.is_ai:
            role_lines.append(f"  Role {p.role.value}: AI character (invent a fitting persona)")
        else:
            role_lines.append(f"  Role {p.role.value}: {p.display_name}")

    # Distribute turns round-robin across roles
    role_sequence = [p.role.value for p in participants]
    turn_assignments = [role_sequence[i % len(role_sequence)] for i in range(max_turns)]
    turn_plan = ", ".join(f"Turn {i+1}→{r}" for i, r in enumerate(turn_assignments))

    return PROMPT_TEMPLATE.format(
        language=lang_doc["display_name"],
        level=level_doc["code"],
        level_description=level_doc["description"],
        scenario=scenario,
        roles_block="\n".join(role_lines),
        turn_plan=turn_plan,
        max_turns=max_turns*len(participants),  # Total turns across all roles
        native_prompt=lang_doc["native_prompt"],
        roman_prompt=lang_doc["roman_prompt"],
    )


async def generate_conversation(
    language_display: str,
    level_code: str,
    participants: list[Participant],
    prompt: Optional[str] = None,
    max_turns: int = 20,
) -> tuple[str, list[Message]]:
    """
    Returns (resolved_scenario, list[Message]).
    Fetches language and level data from MongoDB.
    """
    # Find language doc by display name
    lang_doc = await languages_col().find_one({"display_name": language_display})
    if not lang_doc:
        raise ValueError(f"Language '{language_display}' not found in database")

    level_doc = await _get_level(level_code)
    scenario = _resolve_scenario(level_doc, lang_doc["code"], prompt)
    ai_prompt = _build_prompt(lang_doc, level_doc, scenario, participants, max_turns)

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = await model.generate_content_async(ai_prompt)
    text = response.text.strip()

    # Strip markdown fences if present
    text = re.sub(r"^```json\s*|^```\s*|```\s*$", "", text, flags=re.MULTILINE).strip()
    raw_turns: list[dict] = json.loads(text)

    if not isinstance(raw_turns, list) or len(raw_turns) != max_turns * len(participants):
        raise ValueError(
            f"Expected {max_turns * len(participants)} turns from AI, got "
            f"{len(raw_turns) if isinstance(raw_turns, list) else type(raw_turns)}"
        )

    messages = [
        Message(
            turn_number=t["turn_number"],
            speaker=Role(t["speaker"]),
            roman_text=t["roman_text"],
            native_text=t["native_text"],
            english_text=t["english_text"],
            hint=t["hint"],
            response=None,
        )
        for t in raw_turns
    ]

    return scenario, messages