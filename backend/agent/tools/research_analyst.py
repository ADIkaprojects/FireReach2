"""
FireReach — Stage 3: Research Analyst (LLM Grounded)

Synthesises Stage 1 + Stage 2 outputs into a structured Account Brief.
Enforces citation grounding — re-invokes with stricter prompt if >40% claims
reference null/missing signal keys.

LLM: Groq Llama 3.3 70B (primary) with Gemini Flash fallback for large contexts.
"""

from __future__ import annotations
import json
import os

from models import AccountBrief, ContactResult, SignalResult
from validators import check_citations
from agent.prompts import RESEARCH_ANALYST_SYSTEM, RESEARCH_ANALYST_RETRY_SUFFIX
from agent.tools.llm_client import chat_completion, count_tokens

MAX_GROQ_TOKENS = 5_800   # leave headroom under the 6k/min limit


async def run_research_analyst(
    company_name: str,
    signals: SignalResult,
    contact: ContactResult,
    icp_description: str,
) -> AccountBrief:
    """
    Generates a grounded Account Brief. Validates citations against actual
    signal data — retries with a stricter prompt if hallucination ratio > 40%.
    """
    signals_json = signals.model_dump_json(exclude_none=False)
    contact_json = contact.model_dump_json(exclude_none=False)

    prompt_tokens = count_tokens(signals_json + contact_json + icp_description)
    use_gemini = prompt_tokens > MAX_GROQ_TOKENS

    user_message = (
        f"Company: {company_name}\n\n"
        f"Signals:\n{signals_json}\n\n"
        f"Contact:\n{contact_json}\n\n"
        f"Seller ICP:\n{icp_description}"
    )

    raw = await chat_completion(
        system=RESEARCH_ANALYST_SYSTEM,
        user=user_message,
        temperature=0.4,
        prefer_gemini=use_gemini,
    )

    brief = _parse_brief(raw)
    brief, stripped_ratio = check_citations(brief, signals)

    if stripped_ratio > 0.40:
        # Fallback: stricter prompt
        raw = await chat_completion(
            system=RESEARCH_ANALYST_SYSTEM + "\n\n" + RESEARCH_ANALYST_RETRY_SUFFIX,
            user=user_message,
            temperature=0.2,
            prefer_gemini=use_gemini,
        )
        brief = _parse_brief(raw)
        brief, _ = check_citations(brief, signals)

    return brief


def _parse_brief(raw: str) -> AccountBrief:
    """Extract JSON from LLM response, stripping any markdown fences."""
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )
    try:
        data = json.loads(cleaned)
        return AccountBrief(
            p1=data.get("p1", ""),
            p2=data.get("p2", ""),
            pain_points=data.get("pain_points", []),
            signal_citations=data.get("signal_citations", []),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        # Graceful degradation — return minimal valid brief
        return AccountBrief(
            p1=cleaned[:500],
            p2="",
            pain_points=[],
            signal_citations=[],
        )


# ─── Tool Schema ──────────────────────────────────────────────────────────────

TOOL_SCHEMA = {
    "name": "tool_research_analyst",
    "description": (
        "Analyses harvested signals against the seller ICP and generates a structured "
        "Account Brief. Every factual claim must cite a key from signals_json."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "signals_json": {
                "type": "string",
                "description": "JSON string from tool_signal_harvester",
            },
            "contact_json": {
                "type": "string",
                "description": "JSON string from tool_contact_resolver",
            },
            "icp_description": {"type": "string"},
        },
        "required": ["company_name", "signals_json", "contact_json", "icp_description"],
    },
}
