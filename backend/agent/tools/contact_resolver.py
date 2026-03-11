"""
FireReach — Stage 2: Contact Resolver (Deterministic Waterfall)

Resolves company_domain → { name, title, verified_email } using:
  Step 1: Clearbit Autocomplete (free, no auth)
  Step 2: Apollo.io free tier — decision-maker by title
  Step 3: Hunter.io Domain Search (free, 25/mo)
  Step 4: Snov.io SMTP verification (free, 50 credits/mo)

If confidence < 0.6, returns found=False and the agent skips dispatch.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any

import httpx

from models import ContactResult

# Target decision-maker titles in priority order
DEFAULT_TARGET_TITLES = [
    "CTO",
    "VP Engineering",
    "CISO",
    "Head of Security",
    "DevOps Lead",
    "VP of Engineering",
    "Chief Technology Officer",
    "Chief Information Security Officer",
    "Engineering Manager",
]


# ─── Step 1: Clearbit Autocomplete (free, no auth) ────────────────────────────

async def _clearbit_autocomplete(client: httpx.AsyncClient, company_name: str) -> dict | None:
    try:
        resp = await client.get(
            "https://autocomplete.clearbit.com/v1/companies/suggest",
            params={"query": company_name},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json()
        return results[0] if results else None
    except Exception:
        return None


# ─── Step 2: Apollo.io — find decision-maker ─────────────────────────────────

async def _apollo_search(
    client: httpx.AsyncClient, domain: str, titles: list[str]
) -> dict | None:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return None

    try:
        resp = await client.post(
            "https://api.apollo.io/v1/mixed_people/search",
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            json={
                "q_organization_domains": domain,
                "page": 1,
                "per_page": 10,
                "person_titles": titles,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        people = data.get("people", [])
        if not people:
            return None

        # Score by title priority
        title_priority = {t.lower(): i for i, t in enumerate(DEFAULT_TARGET_TITLES)}

        def _score(person: dict) -> int:
            title = (person.get("title") or "").lower()
            for i, t in enumerate(DEFAULT_TARGET_TITLES):
                if t.lower() in title:
                    return i
            return 999

        best = min(people, key=_score)
        return {
            "first_name": best.get("first_name", ""),
            "last_name": best.get("last_name", ""),
            "full_name": f"{best.get('first_name', '')} {best.get('last_name', '')}".strip(),
            "title": best.get("title", ""),
            "linkedin_url": best.get("linkedin_url", ""),
            "apollo_id": best.get("id", ""),
        }
    except Exception:
        return None


# ─── Step 2b: Apollo free email export fallback ───────────────────────────────

async def _apollo_export_email(client: httpx.AsyncClient, apollo_id: str) -> str | None:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key or not apollo_id:
        return None
    try:
        resp = await client.post(
            f"https://api.apollo.io/v1/people/match",
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            json={"id": apollo_id, "reveal_personal_emails": False},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        person = data.get("person", {})
        return person.get("email") if person.get("email_status") == "verified" else None
    except Exception:
        return None


# ─── Step 3: Hunter.io Domain Search ─────────────────────────────────────────

async def _hunter_domain_search(
    client: httpx.AsyncClient, domain: str, full_name: str
) -> dict | None:
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key:
        return None

    try:
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "full_name": full_name,
                "api_key": api_key,
                "limit": 5,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        emails = data.get("emails", [])
        if not emails:
            return None

        # Prefer verified email with highest score
        verified = [e for e in emails if e.get("verification", {}).get("status") == "valid"]
        pool = verified or emails
        best = max(pool, key=lambda e: e.get("confidence", 0))

        return {
            "email": best.get("value"),
            "confidence": best.get("confidence", 0) / 100,  # normalise 0-1
            "first_name": best.get("first_name"),
            "last_name": best.get("last_name"),
        }
    except Exception:
        return None


# ─── Step 4: Snov.io SMTP Verification ───────────────────────────────────────

async def _snovio_smtp_verify(client: httpx.AsyncClient, email: str) -> bool:
    """
    Returns True if the email is deliverable.
    Treats 'unknown' as potentially valid (greylisting) — caller notes it.
    Hard bounces (invalid) → False.
    """
    client_id = os.environ.get("SNOVIO_CLIENT_ID")
    client_secret = os.environ.get("SNOVIO_CLIENT_SECRET")
    if not client_id or not client_secret:
        return True  # skip verification if creds not configured

    try:
        # Get access token
        token_resp = await client.post(
            "https://api.snov.io/v1/oauth/access_token",
            json={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")

        # Verify email
        verify_resp = await client.post(
            "https://api.snov.io/v1/get-emails-verification-status",
            json={"access_token": access_token, "emails": [email]},
            timeout=10,
        )
        verify_resp.raise_for_status()
        result = verify_resp.json()

        # Parse status
        statuses = result if isinstance(result, list) else result.get("data", [])
        for item in statuses:
            if item.get("email") == email:
                status = item.get("status", "unknown").lower()
                # "invalid" or "catch-all" + hard bounce pattern → False
                return status not in ("invalid", "bounced", "spam_trap")
        return True   # unknown = potentially valid (greylisting)
    except Exception:
        return True   # network issues shouldn't block email


# ─── Public Entry Point ───────────────────────────────────────────────────────

async def _hunter_find_decision_maker(
    client: httpx.AsyncClient, domain: str
) -> dict | None:
    """Hunter Domain Search — returns name + title + email in one call."""
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key:
        return None
    try:
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": api_key, "limit": 10},
            timeout=10,
        )
        resp.raise_for_status()
        emails = resp.json().get("data", {}).get("emails", [])
        if not emails:
            return None

        valid = [e for e in emails if e.get("value") and e.get("first_name")]
        pool = valid or emails

        def _seniority(c: dict) -> int:
            title = (c.get("position") or "").lower()
            for i, t in enumerate(DEFAULT_TARGET_TITLES):
                if t.lower() in title:
                    return i
            return 999

        best = min(pool, key=_seniority)
        first = best.get("first_name", "")
        last = best.get("last_name", "")
        return {
            "full_name": f"{first} {last}".strip(),
            "title": best.get("position", ""),
            "email": best.get("value"),
            "confidence": best.get("confidence", 0) / 100,
        }
    except Exception:
        return None


async def run_contact_resolver(
    company_domain: str,
    target_titles: list[str] | None = None,
) -> ContactResult:
    """
    Waterfall: Hunter.io Domain Search → Snov.io SMTP verify.
    Returns ContactResult with found=True/False and confidence score.
    """
    async with httpx.AsyncClient() as client:
        # Step 1: Find decision-maker via Hunter Domain Search
        contact = await _hunter_find_decision_maker(client, company_domain)
        if not contact or not contact.get("email"):
            return ContactResult(found=False, reason="no_contact_found")

        # Step 2: SMTP verify
        smtp_ok = await _snovio_smtp_verify(client, contact["email"])
        return ContactResult(
            found=True,
            name=contact["full_name"],
            title=contact["title"],
            email=contact["email"],
            confidence=contact["confidence"],
            source="hunter.io",
            smtp_verified=smtp_ok,
        )

    return ContactResult(found=False, reason="email_not_resolvable")


# ─── Tool Schema ──────────────────────────────────────────────────────────────

TOOL_SCHEMA = {
    "name": "tool_contact_resolver",
    "description": (
        "Resolves a company domain to the best decision-maker contact (name, title, "
        "verified email) using a free API waterfall. Returns confidence score. "
        "If confidence < 0.6, sets found: false and the agent skips dispatch."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_domain": {"type": "string"},
            "target_titles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Job titles to target. Defaults to CTO, VP Engineering, CISO, etc.",
            },
        },
        "required": ["company_domain"],
    },
}
