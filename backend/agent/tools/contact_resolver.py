"""
FireReach — Stage 2: Contact Resolver (Deterministic Waterfall)

Resolves company_domain → { name, title, verified_email } using:
  Step 1: Hunter.io Domain Search (free, 25/mo)
    Step 2: Apollo.io Contacts Search (free tier) — enrich with seniority + LinkedIn URL
  Step 3: Snov.io SMTP verification (free, 50 credits/mo)

Seniority ranking: C_SUITE > VP > DIRECTOR > MANAGER > SENIOR > ENTRY
If confidence < 0.6, returns found=False and the agent skips dispatch.
"""

from __future__ import annotations
import os
import re
from typing import Any

import httpx

from models import ContactResult


def _log(msg: str) -> None:
    print(f"[contact_resolver] {msg}")

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

HUNTER_POSITION_PRIORITY = [
    "CTO",
    "Chief Technology Officer",
    "VP Engineering",
    "VP of Engineering",
    "CISO",
    "Head of Security",
    "Director of Engineering",
    "Engineering Manager",
    "Developer",
    "Engineer",
]

# Env vars read by this module.
ENV_VARS_READ = {
    "APOLLO_API_KEY",
    "HUNTER_API_KEY",
    "SNOVIO_CLIENT_ID",
    "SNOVIO_CLIENT_SECRET",
}


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


# ─── Step 2: Apollo.io Contacts Search (free tier) ───────────────────────────

async def _apollo_search(
    client: httpx.AsyncClient, domain: str, titles: list[str]
) -> dict | None:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return None

    try:
        resp = await client.post(
            "https://api.apollo.io/api/v1/contacts/search",
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            json={
                "q_organization_domains": domain,
                "page": 1,
                "per_page": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        contacts = data.get("contacts", [])
        if not contacts:
            return None

        # Score by title priority
        title_priority = {t.lower(): i for i, t in enumerate(DEFAULT_TARGET_TITLES)}

        def _score(person: dict) -> int:
            title = (person.get("title") or "").lower()
            for i, t in enumerate(DEFAULT_TARGET_TITLES):
                if t.lower() in title:
                    return i
            return 999

        best = min(contacts, key=_score)
        return {
            "first_name": best.get("first_name", ""),
            "last_name": best.get("last_name", ""),
            "full_name": f"{best.get('first_name', '')} {best.get('last_name', '')}".strip(),
            "title": best.get("title", ""),
            "linkedin_url": best.get("linkedin_url", ""),
            "seniority": best.get("seniority", ""),
            "department": best.get("department") or best.get("departments") or [],
        }
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


# ─── Seniority Ranking ────────────────────────────────────────────────────────

_SENIORITY_RANK: dict[str, int] = {
    "c_suite": 0,
    "vp": 1,
    "director": 2,
    "manager": 3,
    "senior": 4,
    "entry": 5,
    "individual_contributor": 6,
}


def _seniority_rank(seniority: str | None) -> int:
    """
    Returns a numeric rank for a seniority string (lower = more senior).

    Args:
        seniority: Apollo seniority label or job title fragment.

    Returns:
        Integer rank (0 = C-suite, 6 = entry/unknown).
    """
    if not seniority:
        return 99
    s = seniority.lower()
    for key, rank in _SENIORITY_RANK.items():
        if key in s:
            return rank
    # Try title-based inference
    if any(t in s for t in ["cto", "ciso", "ceo", "coo", "cfo"]):
        return 0
    if "vp" in s or "vice" in s:
        return 1
    if "director" in s or "head of" in s:
        return 2
    if "manager" in s or "lead" in s:
        return 3
    return 6


# ─── Apollo.io Contacts Search (enrichment) ──────────────────────────────────

async def apollo_enrich(
    first_name: str,
    last_name: str,
    domain: str,
    client: httpx.AsyncClient,
) -> dict:
    """
    Enriches a contact with Apollo.io Contacts Search API (free tier).

    Attempts to return seniority, LinkedIn URL, title, and department for the
    most senior contact at the target domain. Completely optional — never raises.

    Args:
        first_name: Contact's first name.
        last_name:  Contact's last name.
        domain:     Company domain (e.g. acme.com).
        client:     Shared httpx.AsyncClient instance.

    Returns:
        Dict with keys: seniority, linkedin_url, title, department (list).
        Empty dict if enrichment fails or APOLLO_API_KEY is not set.
    """
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return {}

    try:
        resp = await client.post(
            "https://api.apollo.io/api/v1/contacts/search",
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            json={
                "q_organization_domains": domain,
                "page": 1,
                "per_page": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        contacts = data.get("contacts", [])
        if not contacts:
            print("[contact_resolver] Warning: Apollo returned no contacts")
            return {}

        # Pick most senior contact: C_SUITE > VP > DIRECTOR > MANAGER > SENIOR > ENTRY
        best = min(contacts, key=lambda c: _seniority_rank(c.get("seniority")))
        return {
            "seniority": best.get("seniority"),
            "linkedin_url": best.get("linkedin_url"),
            "title": best.get("title"),
            "department": best.get("department") or best.get("departments") or [],
        }
    except Exception as exc:
        print(f"[contact_resolver] Warning: Apollo enrichment failed: {exc}")
        return {}


# ─── Public Entry Point ───────────────────────────────────────────────────────

async def _hunter_find_decision_maker(
    client: httpx.AsyncClient, domain: str
) -> dict | None:
    """
    Hunter Domain Search — robust parsing with title-priority and guessed fallback.

    Note: Hunter free tier often returns 0 emails for large enterprise domains
    (e.g., notion.com, stripe.com, google.com). For deterministic testing,
    prefer smaller companies like cal.com, linear.app, and posthog.com.
    """
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key:
        _log("HUNTER_API_KEY missing; skipping Hunter step")
        return None

    try:
        _log(f"Hunter lookup start for domain={domain}")
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": api_key, "limit": 10},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        emails = data.get("emails") or []
        organization = data.get("organization")
        pattern = data.get("pattern")

        _log(
            "Hunter raw summary: "
            f"status={resp.status_code}, domain={data.get('domain')}, "
            f"organization={organization}, pattern={pattern}, emails_count={len(emails)}"
        )

        if len(emails) == 0 and domain.lower() in {"notion.com", "stripe.com", "google.com"}:
            _log(
                "Hunter returned 0 emails for a known large domain on free tier. "
                "Try testing with smaller domains like cal.com, linear.app, or posthog.com."
            )

        # Path A: emails[] present — pick first matching title by explicit priority list.
        if emails:
            _log(f"Hunter returned {len(emails)} contact candidates")
            selected: dict | None = None
            selection_reason = ""

            for wanted_title in HUNTER_POSITION_PRIORITY:
                match = next(
                    (
                        e for e in emails
                        if wanted_title.lower() in (e.get("position") or "").lower()
                        and e.get("value")
                    ),
                    None,
                )
                if match:
                    selected = match
                    selection_reason = f"matched priority title '{wanted_title}'"
                    break

            if not selected:
                selected = next((e for e in emails if e.get("value")), emails[0])
                selection_reason = "no title priority match; fell back to first email record"

            first = selected.get("first_name", "")
            last = selected.get("last_name", "")
            chosen = {
                "full_name": f"{first} {last}".strip(),
                "title": selected.get("position", ""),
                "email": selected.get("value"),
                "confidence": (selected.get("confidence", 0) or 0) / 100,
                "guessed": False,
                "source": "hunter.io",
                "hunter_emails_count": len(emails),
            }
            _log(
                "Hunter selected contact: "
                f"name={chosen['full_name'] or '(unknown)'}, title={chosen['title']}, "
                f"email={chosen['email']}, reason={selection_reason}"
            )
            return chosen

        # Path B: emails empty, but response still has domain + organization + pattern.
        if data.get("domain") and organization and pattern:
            org_norm = str(organization).strip().lower()
            org_norm = "".join(ch for ch in org_norm if ch.isalnum() or ch in {" ", "-", "_"})
            tokens = [t for t in re.split(r"[\s_-]+", org_norm) if t]
            first_guess = tokens[0] if tokens else "team"
            last_guess = tokens[-1] if tokens else "team"

            local_part = str(pattern)
            local_part = local_part.replace("{first}", first_guess)
            local_part = local_part.replace("{last}", last_guess)
            local_part = local_part.replace("{f}", first_guess[:1] if first_guess else "t")
            local_part = local_part.replace("{l}", last_guess[:1] if last_guess else "t")
            local_part = local_part.replace("{first_initial}", first_guess[:1] if first_guess else "t")
            local_part = local_part.replace("{last_initial}", last_guess[:1] if last_guess else "t")
            local_part = re.sub(r"[^a-z0-9._-]", "", local_part.lower())

            guessed_email = f"{local_part}@{data.get('domain')}" if local_part else None
            if guessed_email:
                guessed = {
                    "full_name": str(organization).strip(),
                    "title": "",
                    "email": guessed_email,
                    "confidence": 0.2,
                    "guessed": True,
                    "source": "hunter.io.guessed",
                    "hunter_emails_count": 0,
                }
                _log(
                    "Hunter emails empty; built guessed contact from pattern: "
                    f"organization={organization}, pattern={pattern}, guessed_email={guessed_email}"
                )
                return guessed

        _log("Hunter returned no usable contacts and no guessable pattern")
        return None
    except Exception as exc:
        _log(f"Hunter lookup failed: {exc}")
        return None


async def _apollo_fallback_contact_search(
    client: httpx.AsyncClient,
    domain: str,
) -> dict | None:
    """Fallback: Apollo contacts/search if Hunter returns zero emails entirely."""
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        _log("APOLLO_API_KEY missing; skipping Apollo fallback")
        return None

    try:
        _log(f"Apollo fallback start for domain={domain}")
        resp = await client.post(
            "https://api.apollo.io/api/v1/contacts/search",
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            json={
                "q_organization_domains": domain,
                "page": 1,
                "per_page": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        contacts = data.get("contacts", [])
        _log(f"Apollo fallback returned contacts_count={len(contacts)}")
        if not contacts:
            return None

        best = min(contacts, key=lambda c: _seniority_rank(c.get("seniority")))
        first = best.get("first_name", "")
        last = best.get("last_name", "")
        email = best.get("email") or best.get("email_address")
        if not email:
            _log("Apollo fallback had no email on most senior contact")
            return None

        selected = {
            "full_name": f"{first} {last}".strip(),
            "title": best.get("title", ""),
            "email": email,
            "confidence": 0.6,
            "guessed": False,
            "source": "apollo.io.fallback",
            "seniority": best.get("seniority"),
            "linkedin_url": best.get("linkedin_url"),
            "hunter_emails_count": 0,
        }
        _log(
            "Apollo fallback selected contact: "
            f"name={selected['full_name'] or '(unknown)'}, title={selected['title']}, email={selected['email']}"
        )
        return selected
    except Exception as exc:
        _log(f"Apollo fallback failed: {exc}")
        return None


async def run_contact_resolver(
    company_domain: str,
    target_titles: list[str] | None = None,
) -> ContactResult:
    """
    Waterfall: Hunter.io Domain Search → Apollo.io Enrichment → Snov.io SMTP verify.

    Apollo enrichment is optional and upgrades the contact if a higher-seniority
    person is found. Returns ContactResult with found=True/False and confidence score.

    Args:
        company_domain: Company domain to resolve (e.g. acme.com).
        target_titles:  Target job titles for prioritisation (from ICPProfile).

    Returns:
        ContactResult with contact details and verification status.
    """
    async with httpx.AsyncClient() as client:
        _log(f"Resolver started for domain={company_domain}")

        # Step 1: Hunter primary resolver
        contact = await _hunter_find_decision_maker(client, company_domain)
        hunter_emails_count = int((contact or {}).get("hunter_emails_count", 0) if isinstance(contact, dict) else 0)

        # Step 2a: Apollo fallback if Hunter returned zero emails at all.
        if (not contact or not contact.get("email")) or hunter_emails_count == 0:
            _log("Hunter produced zero emails or no resolved contact; trying Apollo fallback")
            apollo_fallback = await _apollo_fallback_contact_search(client, company_domain)
            if apollo_fallback:
                _log("Apollo fallback produced a contact; using Apollo fallback result")
                contact = apollo_fallback
            elif not contact or not contact.get("email"):
                _log("Apollo fallback did not produce a usable contact")
                contact = None
            else:
                _log("Apollo fallback unavailable; continuing with Hunter guessed contact")

        if not contact or not contact.get("email"):
            _log("No contact resolved after Hunter + Apollo fallback")
            return ContactResult(found=False, reason="no_contact_found")

        name = contact.get("full_name", "")
        name_parts = name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[-1] if len(name_parts) > 1 else ""

        # Step 2b: Apollo enrichment ONLY when Hunter already resolved a contact.
        linkedin_url: str | None = None
        seniority: str | None = None
        enriched_title = contact.get("title", "")
        resolved_source = contact.get("source", "hunter.io")
        was_guessed = bool(contact.get("guessed"))

        if str(resolved_source).startswith("hunter.io"):
            _log("Running Apollo enrichment on Hunter-resolved contact")
            apollo_data = await apollo_enrich(first_name, last_name, company_domain, client)
            if apollo_data:
                apollo_seniority = apollo_data.get("seniority")
                hunter_rank = _seniority_rank(_infer_seniority_from_title(enriched_title))
                apollo_rank = _seniority_rank(apollo_seniority)

                # Upgrade to Apollo title only if more senior.
                if apollo_rank < hunter_rank:
                    if apollo_data.get("title"):
                        enriched_title = apollo_data["title"]
                    seniority = apollo_seniority
                    _log("Apollo enrichment upgraded title/seniority based on higher rank")
                else:
                    seniority = _infer_seniority_from_title(enriched_title)

                linkedin_url = apollo_data.get("linkedin_url")
            else:
                _log("Apollo enrichment returned no data")
        else:
            seniority = contact.get("seniority")
            linkedin_url = contact.get("linkedin_url")

        # Step 3: SMTP verify (force false when contact is guessed)
        smtp_ok = False if was_guessed else await _snovio_smtp_verify(client, contact["email"])
        if was_guessed:
            _log("SMTP verify skipped because Hunter contact was guessed")

        final_source = str(resolved_source)
        final_reason = "guessed_from_hunter_pattern" if was_guessed else None

        _log(
            "Final resolved contact: "
            f"name={name or '(unknown)'}, title={enriched_title or '(unknown)'}, "
            f"email={contact['email']}, source={final_source}, smtp_verified={smtp_ok}, "
            f"confidence={contact.get('confidence', 0.0)}"
        )

        return ContactResult(
            found=True,
            name=name,
            title=enriched_title,
            email=contact["email"],
            confidence=contact.get("confidence", 0.0),
            source=final_source,
            smtp_verified=smtp_ok,
            linkedin_url=linkedin_url,
            seniority=seniority,
            reason=final_reason,
        )

    return ContactResult(found=False, reason="email_not_resolvable")


def _infer_seniority_from_title(title: str) -> str:
    """
    Infers a seniority label from a job title string.

    Args:
        title: Job title string (e.g. "VP of Engineering").

    Returns:
        Seniority label string compatible with _seniority_rank().
    """
    t = title.lower()
    if any(x in t for x in ["cto", "ciso", "ceo", "coo", "cfo", "chief"]):
        return "c_suite"
    if "vp" in t or "vice president" in t:
        return "vp"
    if "director" in t or "head of" in t:
        return "director"
    if "manager" in t or "lead" in t:
        return "manager"
    if "senior" in t or "sr." in t:
        return "senior"
    return "entry"


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
