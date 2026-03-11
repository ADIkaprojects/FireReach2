"""
FireReach — Validators
  • Citation checker: strips hallucinated signal keys from AccountBrief
  • Email linter: word count + cliché detector + auto-retry helper
"""

from __future__ import annotations
import re
from models import AccountBrief, SignalResult

# ─── Cliché patterns to detect & reject ──────────────────────────────────────

CLICHE_PATTERNS: list[str] = [
    r"hope\s+this\s+(email\s+)?finds\s+you",
    r"i\s+wanted\s+to\s+reach\s+out",
    r"touching\s+base",
    r"circling\s+back",
    r"\bsynergy\b",
    r"per\s+my\s+last\s+email",
    r"as\s+per",
    r"just\s+following\s+up",
    r"i\s+hope\s+you('re|\s+are)\s+doing\s+well",
    r"quick\s+(question|note|call)",
    r"i\s+came\s+across\s+your\s+(company|profile)",
    r"i\s+think\s+we\s+could\s+be\s+a\s+great\s+fit",
]


# ─── Email Linter ─────────────────────────────────────────────────────────────

def validate_email(text: str) -> tuple[bool, list[str]]:
    """
    Returns (is_valid, list_of_errors).
    Max 200 words, min 60 words, zero clichés.
    """
    errors: list[str] = []
    words = len(text.split())

    if words > 200:
        errors.append(f"Too long: {words} words (max 200)")
    if words < 60:
        errors.append(f"Too short: {words} words (min 60)")

    for pattern in CLICHE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            errors.append(f"Cliché detected: '{pattern}'")

    return len(errors) == 0, errors


# ─── Citation Checker ─────────────────────────────────────────────────────────

def check_citations(
    brief: AccountBrief,
    signals: SignalResult,
) -> tuple[AccountBrief, float]:
    """
    Validates that every key in brief.signal_citations exists in the
    non-null signal result keys. Returns (brief, stripped_ratio).
    """
    valid_keys = set(signals.non_null_keys())
    cited = set(brief.signal_citations)
    invalid = cited - valid_keys
    stripped_ratio = len(invalid) / max(len(cited), 1)

    # Remove invalid citations so the agent doesn't reference missing data
    brief.signal_citations = list(cited - invalid)

    return brief, stripped_ratio


# ─── Signal Sanitiser (Prompt Injection Defence) ──────────────────────────────

INJECTION_PATTERNS: list[str] = [
    r"ignore.{0,20}(previous|above|all).{0,20}(instruction|prompt)",
    r"(reveal|output|print|show).{0,10}(system\s+prompt|api\s+key)",
    r"\byou\s+are\s+now\b",
    r"\bdisregard\b",
    r"\bnew\s+persona\b",
    r"override\s+(previous|all)\s+(instructions?|commands?)",
    r"act\s+as\s+(a\s+)?(?!a\s+senior)",     # "act as DAN" etc.
]


def sanitise_signal_text(text: str) -> str:
    """
    Redacts prompt-injection attempts embedded in harvested signal data.
    Called on every string value before it enters the LLM context.
    """
    for pattern in INJECTION_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def sanitise_signal_dict(data: dict) -> dict:
    """
    Recursively sanitises all string values in a signal dictionary.
    """
    sanitised: dict = {}
    for k, v in data.items():
        if isinstance(v, str):
            sanitised[k] = sanitise_signal_text(v)
        elif isinstance(v, dict):
            sanitised[k] = sanitise_signal_dict(v)
        elif isinstance(v, list):
            sanitised[k] = [
                sanitise_signal_text(item) if isinstance(item, str)
                else sanitise_signal_dict(item) if isinstance(item, dict)
                else item
                for item in v
            ]
        else:
            sanitised[k] = v
    return sanitised
