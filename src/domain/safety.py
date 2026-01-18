"""
Brand-safety filter for Pulse (demo).

Goal:
- Filter out topics we do NOT want to use as a marketing hook.
- Keep it deterministic (rule-based), not LLM-based.
 LLM is not allowed to monetize tragedies/politics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class SafetyResult:
    allowed: List[str]
    blocked: List[Tuple[str, str]]  # (text, reason)


# Very small demo list. You can expand later.
# Keep Turkish + common variants.
BLOCK_PATTERNS: list[tuple[str, str]] = [
    # Politics
    (r"\b(seçim|siyaset|parti|cumhurbaşkan|bakan|meclis)\b", "politics"),
    # Terror / violence / accidents / death
    (r"\b(terör|bomb(a|alı)|patlama|saldırı|çatışma)\b", "terror/violence"),
    (r"\b(kaza|yangın|çökme|deprem|sel|facia)\b", "disaster/accident"),
    (r"\b(ölüm|öldü|cenaze|cinayet|intihar)\b", "death/crime"),
    # Adult / explicit
    (r"\b(erotik|18)\b", "adult"),
]

# Optional: low-quality / spammy signals
LOW_VALUE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(kazanın|bedava|ücretsiz para|kolay para)\b", "spam/scam"),
]


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def filter_texts(texts: Iterable[str]) -> SafetyResult:
    allowed: List[str] = []
    blocked: List[Tuple[str, str]] = []

    for raw in texts:
        t = _norm(raw)
        if not t:
            continue

        blocked_reason = None

        for pat, reason in BLOCK_PATTERNS:
            if re.search(pat, t, flags=re.IGNORECASE):
                blocked_reason = reason
                break

        if blocked_reason:
            blocked.append((t, blocked_reason))
            continue

        for pat, reason in LOW_VALUE_PATTERNS:
            if re.search(pat, t, flags=re.IGNORECASE):
                blocked_reason = reason
                break

        if blocked_reason:
            blocked.append((t, blocked_reason))
            continue

        allowed.append(t)

    seen = set()
    uniq_allowed: List[str] = []
    for t in allowed:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_allowed.append(t)

    return SafetyResult(allowed=uniq_allowed, blocked=blocked)
