"""
FireReach — ICP Scoring Engine (Signal Verification System)

Implements the Signal Verification flow from the whiteboard.
Produces a 0–100 numeric score for each target company based on how well
harvested signals match the seller's Ideal Customer Profile.

Scoring weights:
  Recent funding (≤ 90 days)  : 25 pts
  Hiring in target dept        : 20 pts
  Tech stack match             : 15 pts
  Company size within range    : 15 pts
  Industry / vertical match    : 10 pts
  News / growth mentions       : 10 pts
  Geography match              : 5 pts
  ─────────────────────────────────────
  Total                        : 100 pts

Tiers:
  80–100  🔥 hot        → send email immediately
  55–79   ⚡ warm       → send email with nurture tag
  30–54   🌤 potential  → queue for 30-day review, skip email
  0–29    ❌ poor_fit   → skip entirely, log reason
"""

from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

from models import ICPProfile, SignalResult
from agent.tools.llm_client import chat_completion


# ─── Seniority helpers ────────────────────────────────────────────────────────

_SIZE_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")


def _parse_size_range(size_range: str) -> Optional[tuple[int, int]]:
    """
    Parses a size range string like '50-200' into (50, 200).

    Args:
        size_range: String like '50-200' or '1000+'.

    Returns:
        Tuple (min, max) or None if unparseable.
    """
    m = _SIZE_RANGE_RE.search(size_range)
    if m:
        return int(m.group(1)), int(m.group(2))
    if size_range.endswith("+"):
        try:
            val = int(size_range.rstrip("+").strip())
            return val, 999_999
        except ValueError:
            pass
    return None


def _days_since(date_str: str | None) -> int | None:
    """
    Returns how many days ago the given ISO date string was.

    Args:
        date_str: ISO-format date string or None.

    Returns:
        Number of days since that date, or None if unparseable.
    """
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(tz=timezone.utc) - dt).days
        except ValueError:
            continue
    return None


def _title_matches_targets(title: str, target_titles: list[str]) -> bool:
    """
    Returns True if a job title matches any of the target titles.

    Args:
        title:         Job title string to check.
        target_titles: List of target title strings from ICPProfile.

    Returns:
        True if any target title is a substring of the given title (case-insensitive).
    """
    title_lower = title.lower()
    return any(t.lower() in title_lower for t in target_titles)


# ─── Scoring functions ────────────────────────────────────────────────────────

def _score_funding(signals: SignalResult) -> tuple[int, str]:
    """
    Awards 25 pts for funding within last 90 days, 12 for within 180 days.

    Args:
        signals: Harvested signal data.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    funding = signals.funding
    if not funding or not funding.round:
        return 0, "No recent funding found"

    days = _days_since(funding.date or funding.fetched_at)
    if days is not None and days <= 90:
        return 25, f"Recent funding: {funding.round} (≤ 90 days ago)"
    elif days is not None and days <= 180:
        return 12, f"Recent funding: {funding.round} (≤ 180 days ago)"
    elif funding.round:
        return 8, f"Funding round found: {funding.round} (date unknown)"
    return 0, "No qualifying funding signal"


def _score_hiring(signals: SignalResult, icp: ICPProfile) -> tuple[int, str]:
    """
    Awards up to 20 pts based on open roles in the target department.

    Args:
        signals: Harvested signal data.
        icp:     ICPProfile containing target_titles.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    roles = signals.hiring_roles
    if not roles:
        return 0, "No open roles found"

    # Check for roles matching ICP target titles
    target_roles = [r for r in roles if _title_matches_targets(r.title, icp.target_titles)]

    # Also check security signal if available
    security_hiring = False
    if signals.security_signal and signals.security_signal.get("security_hiring"):
        security_hiring = True

    if target_roles:
        count = len(target_roles)
        pts = min(20, 10 + count * 3)
        return pts, f"Hiring in target dept: {count} role(s) matching {icp.target_titles}"
    elif security_hiring:
        return 12, "Hiring security/compliance roles (S3 signal)"
    elif roles:
        return 5, f"General hiring activity: {len(roles)} open role(s)"
    return 0, "No relevant hiring signals"


def _score_tech_stack(signals: SignalResult, icp: ICPProfile) -> tuple[int, str]:
    """
    Awards up to 15 pts for tech-stack relevance to the ICP product.

    Args:
        signals: Harvested signal data.
        icp:     ICPProfile with your_product and pain_points.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    stack = signals.tech_stack
    if not stack:
        return 0, "No tech stack data"

    # Build a keyword set from the ICP product and pain points
    icp_keywords = set(
        w.lower() for phrase in [icp.your_product, icp.pain_points]
        for w in re.split(r"\W+", phrase) if len(w) > 3
    )
    stack_lower = {t.lower() for t in stack}

    matches = [t for t in stack if any(kw in t.lower() for kw in icp_keywords)]
    if matches:
        return 15, f"Tech stack match: {', '.join(matches[:3])}"

    # Count total stack size as signal of sophistication
    if len(stack) >= 10:
        return 5, f"Rich tech stack ({len(stack)} tools detected)"
    elif stack:
        return 3, f"Tech stack present ({len(stack)} tools)"
    return 0, "No relevant tech stack match"


def _score_company_size(signals: SignalResult, icp: ICPProfile) -> tuple[int, str]:
    """
    Awards 15 pts if company size is within the ICP size range.
    Falls back on hiring role count as a proxy.

    Args:
        signals: Harvested signal data.
        icp:     ICPProfile with size_range.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    size_bounds = _parse_size_range(icp.size_range)
    if not size_bounds:
        return 7, f"Size range unparseable: {icp.size_range}"

    lo, hi = size_bounds
    # Use hiring activity as a proxy: 5+ roles ≈ mid-size company
    hiring_count = len(signals.hiring_roles)
    if hiring_count >= 5 and lo <= 200:
        return 15, f"Hiring volume ({hiring_count} roles) consistent with {icp.size_range}"
    elif hiring_count >= 2:
        return 8, f"Some hiring activity ({hiring_count} roles)"

    # If funding was found, assume they're actively scaling
    if signals.funding and signals.funding.round:
        return 7, f"Funded company — likely within {icp.size_range}"
    return 3, "Insufficient data to verify company size"


def _score_industry(signals: SignalResult, icp: ICPProfile) -> tuple[int, str]:
    """
    Awards 10 pts if industry signals mention the ICP industry vertical.

    Args:
        signals: Harvested signal data.
        icp:     ICPProfile with industry.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    industry_kw = icp.industry.lower()
    text_sources = []
    if signals.news and signals.news.headline:
        text_sources.append(signals.news.headline.lower())
    if signals.funding and signals.funding.source_url:
        text_sources.append(signals.funding.source_url.lower())

    combined = " ".join(text_sources)
    if industry_kw in combined or any(
        alt in combined for alt in _industry_aliases(icp.industry)
    ):
        return 10, f"Industry match: {icp.industry}"
    # Partial credit if any tech or hiring suggests the vertical
    return 4, f"Industry {icp.industry} unconfirmed from signals"


def _industry_aliases(industry: str) -> list[str]:
    """
    Returns common synonyms / abbreviations for a given industry string.

    Args:
        industry: Industry name from ICPProfile.

    Returns:
        List of lowercase alias strings.
    """
    mapping: dict[str, list[str]] = {
        "saas": ["software", "cloud", "platform", "app"],
        "fintech": ["financial", "payment", "banking", "finance"],
        "healthcare": ["health", "medical", "pharma", "biotech", "clinical"],
        "e-commerce": ["retail", "ecommerce", "shop", "merchant"],
        "cybersecurity": ["security", "infosec", "soc", "xdr", "siem"],
    }
    return mapping.get(industry.lower(), [])


def _score_news(signals: SignalResult) -> tuple[int, str]:
    """
    Awards 10 pts for recent, positive news/growth mentions.

    Args:
        signals: Harvested signal data.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    news = signals.news
    market = signals.market_signal

    score = 0
    details = []

    if news and news.headline:
        score += 6
        details.append(f"News: {news.headline[:80]}")

    if market:
        count = market.get("mention_count", 0)
        articles = market.get("news_articles", [])
        if count >= 3 or len(articles) >= 3:
            score += 4
            details.append(f"Market mentions: {count} articles")
        elif count >= 1 or articles:
            score += 2
            details.append("Low market signal")

    score = min(score, 10)
    return score, "; ".join(details) if details else "No news signals"


def _score_geography(signals: SignalResult, icp: ICPProfile) -> tuple[int, str]:
    """
    Awards 5 pts if geography matches ICP geographies.

    Args:
        signals: Harvested signal data.
        icp:     ICPProfile with geography list.

    Returns:
        Tuple of (points_awarded: int, detail: str).
    """
    if not icp.geography or "global" in [g.lower() for g in icp.geography]:
        return 5, "Geography: Global — always matches"

    # Look for geography mentions in news and funding sources
    geo_text = ""
    if signals.news and signals.news.headline:
        geo_text += signals.news.headline.lower()
    if signals.funding and signals.funding.source_url:
        geo_text += signals.funding.source_url.lower()

    geo_kws: dict[str, list[str]] = {
        "us": ["usa", "us ", "america", ".com", "united states"],
        "europe": ["europe", "eu ", "uk", "germany", "france", ".eu", ".co.uk"],
        "india": ["india", ".in", "bangalore", "mumbai", "hyderabad"],
        "asia": ["asia", "singapore", "japan", "china", "korea"],
    }

    for geo in icp.geography:
        aliases = geo_kws.get(geo.lower(), [geo.lower()])
        if any(a in geo_text for a in aliases):
            return 5, f"Geography match: {geo}"

    return 2, f"Geography unconfirmed for {icp.geography}"


# ─── LLM why_now generator ────────────────────────────────────────────────────

async def _generate_why_now(
    company: str,
    signals: SignalResult,
    icp: ICPProfile,
    breakdown: dict,
) -> str:
    """
    Uses an LLM to generate a concise 2-line 'why now' explanation.

    Args:
        company:   Target company name.
        signals:   Harvested signal data.
        icp:       Seller's ICPProfile.
        breakdown: Per-signal score breakdown dict.

    Returns:
        A 1-2 sentence string explaining the timing opportunity.
    """
    signal_summary = "; ".join(
        f"{k}: {v['detail']}"
        for k, v in breakdown.items()
        if v.get("points", 0) > 0
    )
    if not signal_summary:
        return "No strong timing signals detected."

    try:
        prompt = (
            f"Company: {company}\n"
            f"Seller product: {icp.your_product}\n"
            f"Signals found: {signal_summary}\n\n"
            "In exactly 1-2 sentences, explain WHY NOW is the right time to reach out. "
            "Be specific. Reference actual signals. No fluff."
        )
        return await chat_completion(
            system="You are a concise GTM analyst. Output 1-2 plain-text sentences only.",
            user=prompt,
            temperature=0.3,
            task_type="score",
        )
    except Exception:
        return signal_summary[:200]


# ─── Red flag detector ────────────────────────────────────────────────────────

def _detect_red_flags(signals: SignalResult, icp: ICPProfile) -> list[str]:
    """
    Identifies disqualifying signals for the given ICP.

    Args:
        signals: Harvested signal data.
        icp:     Seller's ICPProfile.

    Returns:
        List of red-flag description strings.
    """
    flags = []

    # No contact signals at all
    if not signals.hiring_roles and not signals.funding and not signals.news:
        flags.append("No live signals found — company may be dormant or private")

    # Funding indicates wrong stage
    if signals.funding and signals.funding.round:
        stage_lower = icp.funding_stage.lower()
        round_lower = (signals.funding.round or "").lower()
        if stage_lower in ("series a", "seed") and "series c" in round_lower:
            flags.append(f"Company at {signals.funding.round} — may be above ICP funding stage")
        if stage_lower == "bootstrapped" and any(
            s in round_lower for s in ["series", "seed", "ipo"]
        ):
            flags.append(f"Company is funded ({signals.funding.round}) — ICP targets bootstrapped")

    # Sales signal shows recent competitor deal
    if signals.sales_signal:
        deals = signals.sales_signal.get("deal_mentions", [])
        if deals:
            flags.append(f"Recent deal announcement — may have just signed a competitor")

    return flags


# ─── Public entry point ───────────────────────────────────────────────────────

async def score_icp_fit(signals: SignalResult, icp: ICPProfile) -> dict:
    """
    Scores how well harvested signals match the seller's ICP (0–100).

    Weights:
      Recent funding (≤ 90 days): 25 pts
      Hiring in target department: 20 pts
      Tech stack match:           15 pts
      Company size match:         15 pts
      Industry match:             10 pts
      News / growth mentions:     10 pts
      Geography match:             5 pts

    Args:
        signals: Harvested SignalResult from Stage 1.
        icp:     Seller's ICPProfile.

    Returns:
        Dict with keys:
            total_score (int 0–100),
            tier (str: "hot" | "warm" | "potential" | "poor_fit"),
            breakdown (dict: per-signal points + detail),
            why_now (str: LLM-generated reason),
            red_flags (list[str]).
    """
    funding_pts, funding_detail = _score_funding(signals)
    hiring_pts, hiring_detail = _score_hiring(signals, icp)
    tech_pts, tech_detail = _score_tech_stack(signals, icp)
    size_pts, size_detail = _score_company_size(signals, icp)
    industry_pts, industry_detail = _score_industry(signals, icp)
    news_pts, news_detail = _score_news(signals)
    geo_pts, geo_detail = _score_geography(signals, icp)

    total = (
        funding_pts + hiring_pts + tech_pts + size_pts
        + industry_pts + news_pts + geo_pts
    )
    total = max(0, min(100, total))

    if total >= 80:
        tier = "hot"
    elif total >= 55:
        tier = "warm"
    elif total >= 30:
        tier = "potential"
    else:
        tier = "poor_fit"

    breakdown = {
        "funding":  {"points": funding_pts,  "max": 25, "detail": funding_detail},
        "hiring":   {"points": hiring_pts,   "max": 20, "detail": hiring_detail},
        "tech":     {"points": tech_pts,     "max": 15, "detail": tech_detail},
        "size":     {"points": size_pts,     "max": 15, "detail": size_detail},
        "industry": {"points": industry_pts, "max": 10, "detail": industry_detail},
        "news":     {"points": news_pts,     "max": 10, "detail": news_detail},
        "geography":{"points": geo_pts,      "max": 5,  "detail": geo_detail},
    }

    why_now = await _generate_why_now(
        company=icp.your_product,  # Use product name in context
        signals=signals,
        icp=icp,
        breakdown=breakdown,
    )

    red_flags = _detect_red_flags(signals, icp)

    return {
        "total_score": total,
        "tier": tier,
        "breakdown": breakdown,
        "why_now": why_now,
        "red_flags": red_flags,
    }
