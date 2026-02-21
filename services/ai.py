"""
AI service — generates conversations using Google Gemini.

Each conversation has exactly 20 turns distributed evenly across
the real participant roles (A, B, C, D). AI-only roles are included
in the prompt so the output is self-contained.
"""

import json
import re
from typing import Optional
import google.generativeai as genai
from core.config import settings
from models.schemas import Language, Level, Participant, Message, Role

genai.configure(api_key=settings.google_api_key)

# ── Language-specific generation notes ──────────────────────────────────────

LANGUAGE_NOTES = {
    Language.russian: (
        "Write native_text in standard Cyrillic script. "
        "Write roman_text as a faithful transliteration using standard Latin characters."
    ),
    Language.chinese: (
        "Write native_text in simplified Chinese characters. "
        "Write roman_text in Pinyin WITH tone marks (e.g. nǐ hǎo, māo). No characters in roman_text."
    ),
    Language.swedish: (
        "Swedish uses the Latin alphabet. roman_text and native_text should be identical "
        "(both the standard Swedish orthography)."
    ),
}

LEVEL_DESCRIPTIONS = {
    Level.a1: "absolute beginner — very short sentences, present tense, basic greetings and nouns only",
    Level.a2: "elementary — simple everyday phrases, basic past tense, limited vocabulary",
    Level.b1: "intermediate — handles most everyday situations, some complex sentences",
    Level.b2: "upper-intermediate — fluent in most situations, wider vocabulary, some idioms",
    Level.c1: "advanced — nuanced expression, idiomatic language, complex grammar structures",
    Level.c2: "mastery — near-native, sophisticated vocabulary and style",
}

DEFAULT_SCENARIOS = {
    Language.russian: {
        Level.a1: "Two strangers introduce themselves at a bus stop.",
        Level.a2: "Two friends decide what to have for lunch.",
        Level.b1: "Two colleagues discuss their weekend plans.",
        Level.b2: "Two friends debate city life versus countryside living.",
        Level.c1: "Two people discuss the influence of social media on modern society.",
        Level.c2: "Two authors debate the role of literature in shaping national identity.",
    },
    Language.chinese: {
        Level.a1: "Two classmates greet each other on the first day of school.",
        Level.a2: "Two people order food at a small restaurant.",
        Level.b1: "Two friends plan a short trip together.",
        Level.b2: "Two colleagues discuss a challenging project at work.",
        Level.c1: "Two people debate the pros and cons of rapid urbanisation.",
        Level.c2: "Two scholars discuss Chinese philosophy and its modern relevance.",
    },
    Language.swedish: {
        Level.a1: "Two neighbours meet for the first time.",
        Level.a2: "Two friends talk about their hobbies.",
        Level.b1: "Two people discuss Swedish weather and outdoor activities.",
        Level.b2: "Two colleagues talk about work-life balance in Sweden.",
        Level.c1: "Two friends discuss the Swedish welfare system.",
        Level.c2: "Two journalists debate the role of the press in a democracy.",
    },
}


def _resolve_scenario(language: Language, level: Level, prompt: Optional[str]) -> str:
    if prompt and prompt.strip():
        return prompt.strip()
    return DEFAULT_SCENARIOS[language][level]


def _build_prompt(
    language: Language,
    level: Level,
    scenario: str,
    participants: list[Participant],
) -> str:
    lang_note = LANGUAGE_NOTES[language]
    level_desc = LEVEL_DESCRIPTIONS[level]

    # Describe each role
    role_lines = []
    for p in participants:
        if p.is_ai:
            role_lines.append(f"  Role {p.role.value}: AI character (invent a fitting persona)")
        else:
            role_lines.append(f"  Role {p.role.value}: {p.display_name}")

    roles_block = "\n".join(role_lines)

    # Distribute 20 turns evenly across roles in round-robin order
    role_sequence = [p.role.value for p in participants]
    turn_assignments = [role_sequence[i % len(role_sequence)] for i in range(20)]
    turn_plan = ", ".join(f"Turn {i+1}→{r}" for i, r in enumerate(turn_assignments))

    return f"""You are a language learning conversation generator.

Generate a realistic, natural conversation in {language} between the following roles:

{roles_block}

Scenario: "{scenario}"
Language: {language}
Level: {level} ({level_desc})

Turn assignment (follow exactly):
{turn_plan}

Requirements:
- Exactly 20 turns, numbered 1 to 20.
- Each turn follows the assignment above — do not deviate.
- Lines must be appropriate for the {level} level.
- {lang_note}
- english_text is a natural English translation of the line.
- hint is one concise grammar or vocabulary tip relevant to that specific line (max 15 words).
- The conversation must flow naturally and stay on the scenario throughout.

Return ONLY a valid JSON array — no markdown, no explanation, nothing else:
[
  {{
    "turn_number": 1,
    "speaker": "<role letter A/B/C/D>",
    "roman_text": "<line in roman/latin script>",
    "native_text": "<line in native script>",
    "english_text": "<English translation>",
    "hint": "<grammar or vocab tip>"
  }},
  ...
]"""


async def generate_conversation(
    language: Language,
    level: Level,
    participants: list[Participant],
    prompt: Optional[str] = None,
) -> tuple[str, list[Message]]:
    """
    Returns (resolved_scenario, list[Message]).
    Raises ValueError if the AI response cannot be parsed.
    """
    scenario = _resolve_scenario(language, level, prompt)
    ai_prompt = _build_prompt(language, level, scenario, participants)

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = await model.generate_content_async(ai_prompt)
    text = response.text.strip()

    # Strip markdown fences if present
    text = re.sub(r"^```json\s*|^```\s*|```\s*$", "", text, flags=re.MULTILINE).strip()

    raw_turns: list[dict] = json.loads(text)

    if not isinstance(raw_turns, list) or len(raw_turns) != 20:
        raise ValueError(f"Expected 20 turns from AI, got {len(raw_turns) if isinstance(raw_turns, list) else type(raw_turns)}")

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
