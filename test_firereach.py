"""
FireReach v3 — Quick Integration Test
======================================
Runs the full 4-stage pipeline directly (no HTTP server needed) against
a real company and sends the output email via Gmail SMTP.

Usage:
    cd D:\\FireReach
    python test_firereach.py

The script loads backend/.env automatically.
"""

import json
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

# ── Load .env from backend/ ─────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), "backend", ".env"))

# ── Allow importing backend modules ─────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from groq import Groq  # type: ignore

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# ────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Signal Harvester
# ────────────────────────────────────────────────────────────────────────────

def stage_1_signal_harvester(company_name: str, company_domain: str) -> dict:
    print(f"\n📡 [Stage 1] Harvesting signals for {company_name}…")

    signals: dict = {
        "company_name":   company_name,
        "company_domain": company_domain,
        "funding":        None,
        "hiring_roles":   [],
        "tech_stack":     [],
        "news":           None,
        "market_signal":  {"news_articles": [], "mention_count": 0},
    }

    slug = re.sub(r"\.(com|io|ai|co|app|net|org)$", "", company_domain)

    # ── Hiring: Greenhouse ──────────────────────────────────────────────────
    try:
        gh = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=6,
        )
        if gh.status_code == 200:
            jobs = gh.json().get("jobs", [])
            signals["hiring_roles"] = [j["title"] for j in jobs[:8]]
            print(f"   ✅ Greenhouse: {len(jobs)} open roles")
    except Exception as e:
        print(f"   ⚠  Greenhouse: {e}")

    # ── Hiring fallback: Lever ──────────────────────────────────────────────
    if not signals["hiring_roles"]:
        try:
            lv = requests.get(
                f"https://api.lever.co/v0/postings/{slug}",
                timeout=6,
            )
            if lv.status_code == 200:
                jobs = lv.json()
                signals["hiring_roles"] = [j["text"] for j in jobs[:8]]
                print(f"   ✅ Lever: {len(jobs)} open roles")
        except Exception as e:
            print(f"   ⚠  Lever: {e}")

    # ── Funding + News: Tavily ──────────────────────────────────────────────
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            from tavily import TavilyClient  # type: ignore
            tavily = TavilyClient(api_key=tavily_key)

            fr = tavily.search(
                f"{company_name} funding round 2024 OR 2025 OR 2026",
                max_results=2,
            )
            if fr.get("results"):
                signals["funding"] = fr["results"][0]["content"][:300]
                print("   ✅ Tavily: funding signal found")

            nr = tavily.search(
                f"{company_name} growth expansion announcement 2025 OR 2026",
                max_results=2,
            )
            if nr.get("results"):
                signals["news"] = nr["results"][0]["content"][:300]
                print("   ✅ Tavily: news signal found")
        except Exception as e:
            print(f"   ⚠  Tavily: {e}")

    # ── Market Signal: NewsAPI with Tavily fallback ───────────────────────
    try:
        news_key = os.getenv("NEWS_API_KEY")
        if news_key:
            company_token = company_name.lower().strip()
            domain_token = company_domain.split(".")[0].lower().strip()
            from_date = (datetime.now(tz=timezone.utc) - timedelta(days=30)).date().isoformat()
            nr = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": f'"{company_name}" AND ("software" OR "funding" OR "product" OR "startup")',
                    "language": "en",
                    "from": from_date,
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                    "apiKey": news_key,
                },
                timeout=8,
            )
            if nr.status_code == 200:
                data = nr.json()
                raw_articles = [
                    {
                        "title": a.get("title", ""),
                        "description": a.get("description", ""),
                    }
                    for a in data.get("articles", [])[:5]
                ]
                # Keep only articles likely about the target company.
                articles = []
                for a in raw_articles:
                    haystack = f"{a.get('title', '')} {a.get('description', '')}".lower()
                    if company_token in haystack or domain_token in haystack:
                        articles.append(a)

                signals["market_signal"] = {
                    "news_articles": articles,
                    # Use filtered count to avoid misleading totals from broad queries.
                    "mention_count": len(articles),
                }
                if articles:
                    print(f"   ✅ NewsAPI: market signal found ({len(articles)} relevant)")
                else:
                    print("   ⚠  NewsAPI: no relevant articles after filtering — falling back to Tavily")
            else:
                print(f"   ⚠  NewsAPI HTTP {nr.status_code} — falling back to Tavily")
        if signals["market_signal"]["mention_count"] == 0 and tavily_key:
            from tavily import TavilyClient  # type: ignore
            tavily = TavilyClient(api_key=tavily_key)
            tr = tavily.search(f"{company_name} latest news 2025", max_results=5)
            results = tr.get("results", [])
            articles = [
                {
                    "title": r.get("title", ""),
                    "description": r.get("content", ""),
                }
                for r in results[:5]
            ]
            signals["market_signal"] = {
                "news_articles": articles,
                "mention_count": len(articles),
            }
            if articles:
                print("   ✅ Tavily fallback: market signal found")
    except Exception as e:
        print(f"   ⚠  Market signal: {e}")

    # ── Tech Stack: BuiltWith ───────────────────────────────────────────────
    bw_key = os.getenv("BUILTWITH_API_KEY", "free")
    try:
        bw = requests.get(
            f"https://api.builtwith.com/free1/api.json?KEY={bw_key}&LOOKUP={company_domain}",
            timeout=6,
        )
        if bw.status_code == 200:
            techs = (
                bw.json()
                .get("Results", [{}])[0]
                .get("Result", {})
                .get("Paths", [{}])[0]
                .get("Technologies", [])
            )
            signals["tech_stack"] = [t["Name"] for t in techs[:6]]
            print(f"   ✅ BuiltWith: {signals['tech_stack']}")
    except Exception as e:
        print(f"   ⚠  BuiltWith: {e}")

    print(f"\n   📦 Signals collected: {json.dumps(signals, indent=2)}")
    return signals

# ────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Contact Resolver
# ────────────────────────────────────────────────────────────────────────────

_TITLE_RANK = [
    "cto", "chief technology officer",
    "vp engineering", "vp of engineering",
    "ciso", "head of security",
    "director of engineering", "engineering manager",
    "developer", "engineer",
]

_SENIORITY_RANK = {
    "c_suite": 0,
    "vp": 1,
    "director": 2,
    "manager": 3,
    "senior": 4,
    "entry": 5,
}


def _title_score(title: str) -> int:
    t = title.lower()
    for i, kw in enumerate(_TITLE_RANK):
        if kw in t:
            return i
    return 999


def _seniority_score(seniority: str) -> int:
    s = (seniority or "").lower()
    for key, rank in _SENIORITY_RANK.items():
        if key in s:
            return rank
    return 999


def _log(msg: str) -> None:
    print(f"   [contact_resolver] {msg}")


def stage_2_contact_resolver(company_domain: str, target_titles: list) -> dict:
    print(f"\n🔍 [Stage 2] Resolving contact for {company_domain}…")

    contact = {
        "found":         False,
        "name":          None,
        "title":         None,
        "email":         None,
        "source":        None,
        "smtp_verified": False,
    }

    hunter_emails_count = 0

    # ── Step 1: Hunter.io domain-search ─────────────────────────────────────
    hunter_key = os.getenv("HUNTER_API_KEY")
    if hunter_key:
        try:
            resp = requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": company_domain, "api_key": hunter_key, "limit": 10},
                timeout=8,
            )
            if resp.status_code == 200:
                payload = resp.json()
                data = payload.get("data", {}) if isinstance(payload, dict) else {}
                emails = data.get("emails") or []
                hunter_emails_count = len(emails)
                organization = data.get("organization")
                pattern = data.get("pattern")

                _log(
                    f"Hunter response: domain={data.get('domain')}, organization={organization}, "
                    f"pattern={pattern}, emails_count={hunter_emails_count}"
                )

                if hunter_emails_count == 0 and company_domain.lower() in {"servicenow.com", "notion.com", "stripe.com", "google.com"}:
                    _log(
                        "Hunter returned 0 emails for a known large domain on free tier. "
                        "Try testing with smaller domains like cal.com, linear.app, or posthog.com."
                    )

                if emails:
                    selected = None
                    reason = ""
                    for wanted in _TITLE_RANK:
                        selected = next(
                            (e for e in emails if wanted in (e.get("position") or "").lower() and e.get("value")),
                            None,
                        )
                        if selected:
                            reason = f"priority title match: {wanted}"
                            break

                    if not selected:
                        selected = next((e for e in emails if e.get("value")), emails[0])
                        reason = "fallback to first email entry"

                    best = selected
                    contact.update({
                        "found":         True,
                        "name":          f"{best.get('first_name','')} {best.get('last_name','')}".strip(),
                        "title":         best.get("position", ""),
                        "email":         best.get("value", ""),
                        "source":        "hunter.io",
                        "smtp_verified": best.get("verification", {}).get("status") == "valid",
                    })
                    _log(f"Hunter selected contact: {contact['name']} <{contact['email']}> ({reason})")
                elif data.get("domain") and organization and pattern:
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
                        contact.update({
                            "found":         True,
                            "name":          str(organization).strip(),
                            "title":         "",
                            "email":         guessed_email,
                            "source":        "hunter.io.guessed",
                            "smtp_verified": False,
                        })
                        _log(f"Hunter guessed contact from pattern: {contact['name']} <{contact['email']}>")
            else:
                print(f"   ⚠  Hunter HTTP {resp.status_code}")
        except Exception as e:
            print(f"   ⚠  Hunter: {e}")

    # ── Step 2a: Apollo fallback if Hunter had zero emails ─────────────────
    apollo_key = os.getenv("APOLLO_API_KEY")
    if apollo_key and hunter_emails_count == 0:
        print(f"   → Trying Apollo.io…")
        try:
            resp = requests.post(
                "https://api.apollo.io/api/v1/contacts/search",
                headers={"Content-Type": "application/json", "X-Api-Key": apollo_key},
                json={
                    "q_organization_domains": company_domain,
                    "page": 1,
                    "per_page": 5,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                contacts = resp.json().get("contacts", [])
                _log(f"Apollo fallback contacts_count={len(contacts)}")
                if contacts:
                    best = min(
                        contacts,
                        key=lambda p: (
                            _seniority_score(p.get("seniority") or ""),
                            _title_score(p.get("title") or ""),
                        ),
                    )
                    first = best.get("first_name", "")
                    last  = best.get("last_name", "")
                    email = best.get("email", "") or ""

                    if email:
                        contact.update({
                            "found":         True,
                            "name":          f"{first} {last}".strip(),
                            "title":         best.get("title", ""),
                            "email":         email,
                            "source":        "apollo.io.fallback",
                            "smtp_verified": True,
                            "seniority":     best.get("seniority", ""),
                            "linkedin_url":  best.get("linkedin_url", ""),
                        })
                        print(f"   ✅ Apollo: {contact['name']} <{contact['email']}>")
                    else:
                        print(f"   ⚠  Apollo found {first} {last} but no email")
            else:
                print(f"   ⚠  Apollo HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"   ⚠  Apollo: {e}")

    # ── Step 2b: Apollo enrichment (only for Hunter-resolved real contacts) ─
    if contact["found"] and contact.get("source") == "hunter.io" and apollo_key:
        _log("Apollo enrichment on Hunter-resolved contact")
        try:
            resp = requests.post(
                "https://api.apollo.io/api/v1/contacts/search",
                headers={"Content-Type": "application/json", "X-Api-Key": apollo_key},
                json={"q_organization_domains": company_domain, "page": 1, "per_page": 5},
                timeout=15,
            )
            if resp.status_code == 200:
                contacts = resp.json().get("contacts", [])
                if contacts:
                    best = min(contacts, key=lambda p: _seniority_score(p.get("seniority") or ""))
                    if best.get("title") and _seniority_score(best.get("seniority") or "") < _title_score(contact.get("title") or ""):
                        contact["title"] = best.get("title", contact.get("title"))
                    contact["seniority"] = best.get("seniority", "")
                    contact["linkedin_url"] = best.get("linkedin_url", "")
                    _log("Apollo enrichment completed")
        except Exception as e:
            _log(f"Apollo enrichment failed: {e}")

    if contact["found"]:
        _log(
            f"Final resolved contact => name={contact.get('name')}, title={contact.get('title')}, "
            f"email={contact.get('email')}, source={contact.get('source')}, smtp_verified={contact.get('smtp_verified')}"
        )
        return contact

    # ── Step 3: Hunter email-finder (uses a name we may have from Apollo) ────
    if hunter_key and contact.get("name"):
        name_parts = (contact["name"] or "").split()
        if len(name_parts) >= 2:
            print(f"   → Hunter email-finder for {contact['name']} @ {company_domain}…")
            try:
                resp = requests.get(
                    "https://api.hunter.io/v2/email-finder",
                    params={
                        "domain":      company_domain,
                        "first_name":  name_parts[0],
                        "last_name":   name_parts[-1],
                        "api_key":     hunter_key,
                    },
                    timeout=8,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    email = data.get("email", "")
                    if email:
                        contact.update({
                            "found":         True,
                            "email":         email,
                            "source":        "hunter-finder",
                            "smtp_verified": data.get("verification", {}).get("status") == "valid",
                        })
                        print(f"   ✅ Hunter finder: {contact['name']} <{contact['email']}>")
            except Exception as e:
                print(f"   ⚠  Hunter email-finder: {e}")

    if not contact["found"]:
        print("   ⚠  No contact resolved — pipeline will skip send")

    return contact


# ────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Research Analyst
# ────────────────────────────────────────────────────────────────────────────

def stage_3_research_analyst(
    company_name: str,
    signals: dict,
    contact: dict,
    icp_description: str,
) -> dict:
    print(f"\n🧠 [Stage 3] Generating account brief for {company_name}…")

    prompt = f"""You are a senior GTM analyst. Analyse the signals below and produce a
structured account brief for a cold outreach email.

SIGNALS:
{json.dumps(signals, indent=2)}

CONTACT:
{json.dumps(contact, indent=2)}

SELLER ICP:
{icp_description}

Respond ONLY in this exact JSON schema — no prose outside the JSON:
{{
  "p1": "1 paragraph: company growth moment, citing 2 specific signals",
  "p2": "1 paragraph: why this contact + ICP alignment, citing 1 signal",
  "pain_points": ["specific pain 1", "specific pain 2"],
  "signal_citations": ["signal_key1", "signal_key2"]
}}

Rules:
- Every factual claim must come from the signals JSON above.
- Never invent numbers, tool names, or role titles not present in signals.
- If a signal key is null or empty, do not reference it.
"""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    brief = json.loads(resp.choices[0].message.content)
    print(f"   ✅ Brief: {brief['p1'][:100]}…")
    return brief


# ────────────────────────────────────────────────────────────────────────────
# STAGE 4 — Outreach Sender (Gmail SMTP)
# ────────────────────────────────────────────────────────────────────────────

def stage_4_outreach_sender(
    recipient_email: str,
    recipient_name: str,
    recipient_title: str,
    brief: dict,
    icp_description: str,
    tone: str = "consultative",
) -> dict:
    print(f"\n📧 [Stage 4] Composing email for {recipient_name} <{recipient_email}>…")

    # ── Compose ─────────────────────────────────────────────────────────────
    compose_prompt = f"""You are an expert B2B cold-email writer.

ACCOUNT BRIEF:
{json.dumps(brief, indent=2)}

RECIPIENT: {recipient_name} ({recipient_title})
SELLER ICP: {icp_description}
TONE: {tone}

Rules (Zero-Template Policy):
- Open with ONE specific signal (funding round or exact job role title)
- Connect 2 signals to a concrete business risk or growth challenge
- Single CTA: 15-minute call or free assessment
- Max 180 words. No bullet points. No "Hope this finds you well" or clichés.
- Subject must be specific, not generic.

Respond ONLY in JSON:
{{
  "subject": "email subject",
  "body": "full plain-text email body"
}}
"""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": compose_prompt}],
        temperature=0.6,
        response_format={"type": "json_object"},
    )
    email = json.loads(resp.choices[0].message.content)

    # ── Lint ─────────────────────────────────────────────────────────────────
    CLICHES = [
        r"hope this finds you",
        r"i wanted to reach out",
        r"touching base",
        r"circling back",
        r"\bsynergy\b",
    ]
    word_count = len(email["body"].split())
    issues = []
    if word_count > 200:
        issues.append(f"Too long: {word_count} words (max 200)")
    for p in CLICHES:
        if re.search(p, email["body"], re.IGNORECASE):
            issues.append(f"Cliché: '{p}'")

    if issues:
        print(f"   ⚠  Lint issues: {issues} — retrying…")
        compose_prompt += f"\n\nPREVIOUS DRAFT FAILED: {issues}\nFix every issue."
        resp2 = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": compose_prompt}],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        email = json.loads(resp2.choices[0].message.content)

    print(f"   ✅ Subject: {email['subject']}")
    print(f"   📝 Preview: {email['body'][:160]}…")

    # ── Send via Gmail SMTP ──────────────────────────────────────────────────
    gmail_from     = os.getenv("GMAIL_FROM")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    actual_to      = recipient_email

    if not actual_to:
        raise ValueError("Recipient email address must not be None or empty")

    if not gmail_from or not gmail_password:
        print("   ⚠  GMAIL_FROM / GMAIL_APP_PASSWORD not set — skipping send")
        return {"status": "not_sent", "subject": email["subject"], "body": email["body"], "to": actual_to}

    html_body = f"<p style='white-space:pre-wrap;font-family:sans-serif'>{email['body']}</p>"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = email["subject"]
    msg["From"]    = gmail_from
    msg["To"]      = actual_to
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_from, gmail_password)
        server.sendmail(gmail_from, actual_to, msg.as_string())

    print(f"\n   ✅ EMAIL SENT → {actual_to}")
    return {"status": "sent", "subject": email["subject"], "body": email["body"], "to": actual_to}


# ────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ────────────────────────────────────────────────────────────────────────────

def run_firereach(
    company_name: str,
    company_domain: str,
    icp_description: str,
    target_titles: list | None = None,
    tone: str = "consultative",
) -> dict:
    print(f"\n🔥 FireReach v3 — starting pipeline")
    print(f"   Target : {company_name} ({company_domain})")
    print(f"   ICP    : {icp_description[:80]}…")
    print("=" * 62)

    if target_titles is None:
        target_titles = ["CTO", "VP Engineering", "CISO", "Head of Security"]

    signals = stage_1_signal_harvester(company_name, company_domain)
    contact = stage_2_contact_resolver(company_domain, target_titles)

    if not contact["found"]:
        print("\n❌ No contact found — pipeline stopped.")
        return {"status": "contact_not_found"}

    brief  = stage_3_research_analyst(company_name, signals, contact, icp_description)
    recipient_name = "there" if contact.get("source") == "hunter.io.guessed" else ((contact["name"] or "").split()[0] or "there")
    result = stage_4_outreach_sender(
        recipient_email=contact["email"],
        recipient_name=recipient_name,
        recipient_title=contact["title"] or "",
        brief=brief,
        icp_description=icp_description,
        tone=tone,
    )

    print("\n" + "=" * 62)
    print("🎉 FireReach Complete!")
    print(f"   Status  : {result['status']}")
    print(f"   To      : {result.get('to', '—')}")
    print(f"   Subject : {result.get('subject', '—')}")
    print("\n📧 Full email body:")
    print("-" * 62)
    print(result.get("body", ""))
    return result


# ────────────────────────────────────────────────────────────────────────────
# TEST CASE — edit values below then run: python test_firereach.py
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_firereach(
        company_name="ServiceNow",
        company_domain="servicenow.com",
        icp_description=(
            "We sell an AI-powered developer documentation platform that auto-generates "
            "and keeps internal wikis in sync with your codebase. Our ICP is engineering "
            "teams at Series B–C+ SaaS companies where knowledge management is scattered "
            "across Confluence, Jira, and Google Docs and onboarding new engineers takes weeks."
        ),
        target_titles=["CTO", "VP Engineering"],
        tone="consultative",
    )
