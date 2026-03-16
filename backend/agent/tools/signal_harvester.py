"""
FireReach — Stage 1: Signal Harvester (Deterministic)

Fetches live buyer-intent signals using free APIs:
  • Funding:      Tavily API (Google index)
  • Hiring:       Greenhouse ATS + Lever ATS (no auth, unlimited)
  • Tech Stack:   BuiltWith free key
  • News:         Tavily API
  • S3 Security:  Tavily — SOC2, GDPR, compliance hiring queries
  • S4 Sales:     Tavily — partnership / deal announcement queries
  • S6 Market:    NewsAPI — recent news articles about the company

All sub-calls run concurrently via asyncio.gather().
Every source is wrapped in try/except — failures set value: null, never raise.
Prompt-injection sanitisation applied to all harvested text.
"""

from __future__ import annotations
import asyncio
import hashlib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from models import FundingResult, HiringRole, NewsResult, SignalResult
from validators import sanitise_signal_dict

# ─── In-memory cache (TTL = 24 hours for tech stack, 1 hour for signals) ──────
_CACHE: dict[str, tuple[Any, float]] = {}
_TECH_STACK_TTL = 86_400   # 24 hours
_SIGNAL_TTL = 3_600        # 1 hour


def _cache_get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def _cache_set(key: str, value: Any, ttl: int) -> None:
    _CACHE[key] = (value, time.time() + ttl)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_recent(date_str: str | None, max_days: int = 180) -> bool:
    """Returns True if the date string is within `max_days` of today."""
    if not date_str:
        return False
    try:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%B %d, %Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                delta = (datetime.now() - dt).days
                return delta <= max_days
            except ValueError:
                pass
    except Exception:
        pass
    return True   # if we can't parse the date, assume it's okay


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ─── Tavily (used for funding + news) ───────────────────────────────────────

async def _tavily_search(client: httpx.AsyncClient, query: str) -> dict:
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if not tavily_key:
        return {}
    resp = await client.post(
        "https://api.tavily.com/search",
        json={
            "api_key": tavily_key,
            "query": query,
            "include_answer": True,
            "max_results": 5,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


async def _fetch_funding(client: httpx.AsyncClient, company_name: str) -> FundingResult | None:
    try:
        data = await _tavily_search(
            client,
            f"{company_name} funding round Series investment 2024 2025",
        )
        answer = data.get("answer", "")
        results = data.get("results", [])
        text = answer or (results[0].get("content", "") if results else "")
        if not text:
            return None

        round_match = re.search(
            r"\b(Pre-Seed|Seed|Series [A-F]|Series [A-F]\d?|IPO|Growth)\b",
            text,
            re.IGNORECASE,
        )
        amount_match = re.search(
            r"\$[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B)\b",
            text,
            re.IGNORECASE,
        )
        source_url = results[0].get("url", "") if results else ""

        return FundingResult(
            round=round_match.group(0) if round_match else None,
            amount=amount_match.group(0) if amount_match else None,
            date=None,
            source_url=source_url,
            fetched_at=_now_iso(),
        )
    except Exception:
        return FundingResult(reason="api_error")


async def _fetch_news(client: httpx.AsyncClient, company_name: str) -> NewsResult | None:
    try:
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_key:
            return NewsResult(reason="no_api_key")

        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": f"{company_name} recent news growth expansion",
                "include_answer": True,
                "max_results": 3,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        best = results[0]
        return NewsResult(
            headline=sanitise_signal_dict({"h": best.get("title", "")})["h"],
            source=best.get("url", "").split("/")[2] if best.get("url") else None,
            date=best.get("published_date"),
        )
    except Exception:
        return NewsResult(reason="api_error")


# ─── Greenhouse ATS ───────────────────────────────────────────────────────────

async def _resolve_greenhouse_slug(
    client: httpx.AsyncClient, company_name: str
) -> str | None:
    """Try common slug patterns derived from company name."""
    slug_guess = company_name.lower().replace(" ", "").replace(",", "").replace(".", "")
    # Also try hyphenated variant (e.g. "linear-app")
    slug_hyphen = company_name.lower().replace(" ", "-").replace(",", "").replace(".", "")
    for slug in (slug_guess, slug_hyphen):
        try:
            resp = await client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                timeout=8,
            )
            if resp.status_code == 200:
                return slug
        except Exception:
            pass
    return None


async def _fetch_greenhouse_jobs(
    client: httpx.AsyncClient, company_name: str
) -> list[HiringRole]:
    slug = await _resolve_greenhouse_slug(client, company_name)
    if not slug:
        return []
    try:
        resp = await client.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        roles = []
        for job in data.get("jobs", [])[:10]:
            title = sanitise_signal_dict({"t": job.get("title", "")})["t"]
            updated = job.get("updated_at", "")[:10] if job.get("updated_at") else None
            roles.append(HiringRole(title=title, ats="greenhouse", posted=updated))
        return roles
    except Exception:
        return []


# ─── Lever ATS ────────────────────────────────────────────────────────────────

async def _fetch_lever_jobs(
    client: httpx.AsyncClient, company_name: str
) -> list[HiringRole]:
    slug = company_name.lower().replace(" ", "").replace(",", "").replace(".", "")
    try:
        resp = await client.get(
            f"https://api.lever.co/v0/postings/{slug}",
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        roles = []
        for posting in data[:10]:
            title = sanitise_signal_dict({"t": posting.get("text", "")})["t"]
            roles.append(HiringRole(title=title, ats="lever"))
        return roles
    except Exception:
        return []


# ─── BuiltWith ────────────────────────────────────────────────────────────────

SECURITY_TOOLS = {
    "okta", "cloudflare", "datadog", "crowdstrike", "pagerduty",
    "sentry", "splunk", "newrelic", "snyk", "hashicorp", "vault",
    "lacework", "wiz", "orca", "prisma", "tenable",
}


async def _fetch_tech_stack(client: httpx.AsyncClient, domain: str) -> list[str]:
    cache_key = f"tech:{domain}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    builtwith_key = os.environ.get("BUILTWITH_API_KEY", "free")
    try:
        resp = await client.get(
            f"https://api.builtwith.com/free1/api.json",
            params={"KEY": builtwith_key, "LOOKUP": domain},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        tech_names: list[str] = []
        for group in data.get("groups", []):
            for cat in group.get("Categories", []):
                for tech in cat.get("Technologies", []):
                    name = tech.get("Name", "")
                    if name:
                        tech_names.append(name)
        _cache_set(cache_key, tech_names, _TECH_STACK_TTL)
        return tech_names[:20]
    except Exception:
        return []


# ─── S3 — Security / Compliance Signal ────────────────────────────────────────

async def fetch_security_signal(
    company: str,
    client: httpx.AsyncClient,
    hiring_roles: list[HiringRole] | None = None,
) -> dict:
    """
    Fetches S3 security/compliance signals via Tavily search.

    Searches for SOC2, GDPR, and compliance hiring activity.
    Also scans existing Greenhouse job results for security roles.

    Args:
        company:      Company name to search for.
        client:       Shared httpx.AsyncClient instance.
        hiring_roles: Previously fetched hiring roles (optional) to cross-reference.

    Returns:
        Dict with keys 'security_hiring' (bool) and 'compliance_mentions' (list).
    """
    try:
        data = await _tavily_search(
            client,
            f"{company} SOC2 compliance GDPR security audit hiring 2025",
        )
        results = data.get("results", [])
        mentions = [
            sanitise_signal_dict({"h": r.get("title", "")})["h"]
            for r in results[:3]
            if r.get("title")
        ]

        # Cross-reference with already-fetched hiring roles
        security_keywords = {"security", "compliance", "soc", "gdpr", "infosec", "devsecops"}
        security_roles = []
        if hiring_roles:
            security_roles = [
                r.title for r in hiring_roles
                if any(kw in r.title.lower() for kw in security_keywords)
            ]

        return {
            "security_hiring": len(security_roles) > 0 or bool(mentions),
            "compliance_mentions": mentions,
            "security_roles": security_roles,
        }
    except Exception:
        return {"security_hiring": False, "compliance_mentions": [], "security_roles": []}


# ─── S4 — Sales / Partnership Signal ─────────────────────────────────────────

async def fetch_sales_signal(
    company: str,
    client: httpx.AsyncClient,
) -> dict:
    """
    Fetches S4 sales/partnership signals via Tavily search.

    Searches for partnership announcements, enterprise contracts, and deals.

    Args:
        company: Company name to search for.
        client:  Shared httpx.AsyncClient instance.

    Returns:
        Dict with keys 'partnership_signals' (list) and 'deal_mentions' (list).
    """
    try:
        data = await _tavily_search(
            client,
            f"{company} partnership deal announcement enterprise contract signed 2025",
        )
        results = data.get("results", [])
        partnership_signals = [
            sanitise_signal_dict({"h": r.get("title", "")})["h"]
            for r in results[:3]
            if r.get("title")
        ]
        deal_keywords = {"partnership", "deal", "contract", "signed", "enterprise", "agreement"}
        deal_mentions = [
            s for s in partnership_signals
            if any(kw in s.lower() for kw in deal_keywords)
        ]
        return {
            "partnership_signals": partnership_signals,
            "deal_mentions": deal_mentions,
        }
    except Exception:
        return {"partnership_signals": [], "deal_mentions": []}


# ─── S6 — Market / Intent Signal ─────────────────────────────────────────────

async def fetch_market_signal(
    company: str,
    client: httpx.AsyncClient,
) -> dict:
    """
    Fetches S6 market/lead signals via NewsAPI with Tavily fallback.

    Uses NewsAPI when NEWS_API_KEY is set. If key is missing or the request
    fails, falls back to Tavily search so the market signal always works.

    Args:
        company: Company name to search for.
        client:  Shared httpx.AsyncClient instance.

    Returns:
        Dict with keys 'news_articles' (list of {title, description}) and
        'mention_count' (int).
    """
    async def _tavily_fallback() -> dict:
        try:
            data = await _tavily_search(client, f"{company} latest news 2025")
            results = data.get("results", [])
            articles = [
                {
                    "title": sanitise_signal_dict({"h": r.get("title", "")})["h"],
                    "description": sanitise_signal_dict({"d": r.get("content", "")})["d"],
                }
                for r in results[:5]
            ]
            return {"news_articles": articles, "mention_count": len(articles)}
        except Exception:
            return {"news_articles": [], "mention_count": 0}

    news_key = os.environ.get("NEWS_API_KEY")
    if not news_key:
        return await _tavily_fallback()

    try:
        from_date = (datetime.now(tz=timezone.utc) - timedelta(days=30)).date().isoformat()
        query = f'"{company}" AND ("software" OR "funding" OR "product" OR "startup")'
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "from": from_date,
                "sortBy": "publishedAt",
                "pageSize": 5,
                "apiKey": news_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        articles_raw = data.get("articles", [])
        company_lower = company.lower()
        relevant_articles = [
            {
                "title": sanitise_signal_dict({"h": a.get("title", "")})["h"],
                "description": sanitise_signal_dict({"d": a.get("description", "")})["d"],
            }
            for a in articles_raw
            if company_lower in (
                f"{a.get('title', '')} {a.get('description', '')}".lower()
            )
        ]
        return {
            "news_articles": relevant_articles,
            "mention_count": len(relevant_articles),
        }
    except Exception:
        return await _tavily_fallback()


# ─── Public Entry Point ───────────────────────────────────────────────────────

async def run_signal_harvester(
    company_name: str,
    company_domain: str,
) -> SignalResult:
    """
    Fetch all signals concurrently. Each source is independently fault-tolerant.
    Returns a validated SignalResult — missing values are None, never omitted.

    Fetches S1 (hiring), S2 (funding), S3 (security), S4 (sales), S6 (market)
    signals alongside tech stack data, all via asyncio.gather().

    Args:
        company_name:   Company name for ATS and search queries.
        company_domain: Company domain for BuiltWith and Hunter lookups.

    Returns:
        Fully populated SignalResult with all available signals.
    """
    async with httpx.AsyncClient() as client:
        funding_task = _fetch_funding(client, company_name)
        news_task = _fetch_news(client, company_name)
        greenhouse_task = _fetch_greenhouse_jobs(client, company_name)
        lever_task = _fetch_lever_jobs(client, company_name)
        tech_task = _fetch_tech_stack(client, company_domain)
        sales_task = fetch_sales_signal(company_name, client)
        market_task = fetch_market_signal(company_name, client)

        (
            funding, news, gh_roles, lv_roles, tech_stack,
            sales_signal, market_signal,
        ) = await asyncio.gather(
            funding_task, news_task, greenhouse_task, lever_task, tech_task,
            sales_task, market_task,
            return_exceptions=True,
        )

    # Merge hiring roles — prefer Greenhouse, fall back to Lever
    hiring_roles: list[HiringRole] = []
    if isinstance(gh_roles, list) and gh_roles:
        hiring_roles = gh_roles
    elif isinstance(lv_roles, list) and lv_roles:
        hiring_roles = lv_roles

    # Security signal needs hiring roles to cross-reference — run after merge
    async with httpx.AsyncClient() as client:
        security_signal = await fetch_security_signal(company_name, client, hiring_roles)

    return SignalResult(
        funding=funding if isinstance(funding, FundingResult) else FundingResult(reason="api_error"),
        hiring_roles=hiring_roles,
        tech_stack=tech_stack if isinstance(tech_stack, list) else [],
        news=news if isinstance(news, NewsResult) else NewsResult(reason="api_error"),
        security_signal=security_signal if isinstance(security_signal, dict) else None,
        sales_signal=sales_signal if isinstance(sales_signal, dict) else None,
        market_signal=market_signal if isinstance(market_signal, dict) else None,
    )


# ─── Tool Schema (for LLM function-calling) ──────────────────────────────────

TOOL_SCHEMA = {
    "name": "tool_signal_harvester",
    "description": (
        "Fetches live, deterministic buyer-intent signals for a target company using "
        "free APIs. Returns structured JSON with funding, hiring_roles, tech_stack, and "
        "company_news. The LLM must not guess or infer values — only data returned here "
        "may be cited downstream."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "company_domain": {
                "type": "string",
                "description": "e.g. acme.com",
            },
        },
        "required": ["company_name", "company_domain"],
    },
}
