"""
Scoring service.

Multi-factor accuracy scoring:
  - Word overlap   (55%) — fraction of target words present in the response
  - Char similarity (45%) — 1 - normalised Levenshtein distance

Returns a score 0-100, a label, and a human-readable breakdown.
"""

import re


def _normalise(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Strip punctuation but keep letters, digits, spaces, and diacritics
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return text


def _levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _word_overlap(input_words: list[str], target_words: list[str]) -> float:
    if not target_words:
        return 1.0
    input_set = set(input_words)
    matched = sum(1 for w in target_words if w in input_set)
    return matched / len(target_words)


def _char_similarity(a: str, b: str) -> float:
    longer = max(len(a), len(b))
    if longer == 0:
        return 1.0
    return 1.0 - _levenshtein(a, b) / longer


def score_response(user_input: str, target: str) -> dict:
    """
    Returns:
        score (int 0-100), label (str), breakdown (str)
    """
    a = _normalise(user_input)
    b = _normalise(target)

    if a == b:
        return {
            "score": 100,
            "label": "Perfect!",
            "breakdown": "Exact match",
        }

    a_words = a.split()
    b_words = b.split()

    wo = _word_overlap(a_words, b_words)
    cs = _char_similarity(a, b)

    raw = wo * 0.55 + cs * 0.45
    score = max(0, min(100, round(raw * 100)))

    if score >= 90:
        label = "Excellent"
    elif score >= 75:
        label = "Great"
    elif score >= 55:
        label = "Almost there"
    elif score >= 35:
        label = "Partial match"
    else:
        label = "Keep practising"

    breakdown = f"Word match {round(wo * 100)}% · Similarity {round(cs * 100)}%"

    return {
        "score": score,
        "label": label,
        "breakdown": breakdown,
    }
