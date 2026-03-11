import os
import json
import re
import asyncio
import requests
from dotenv import load_dotenv
from groq import Groq
import resend

load_dotenv(os.path.join(os.path.dirname(__file__), "backend", ".env"))

# ─── Clients ───────────────────────────────────────────────
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
resend.api_key = os.getenv("RESEND_API_KEY")

# ─── TOOL 1: Signal Harvester ──────────────────────────────
def tool_signal_harvester(company_name: str, company_domain: str) -> dict:
    print(f"\n🔍 [Stage 1] Harvesting signals for {company_name}...")

    signals = {
        "company_name": company_name,
        "company_domain": company_domain,
        "funding": None,
        "hiring_roles": [],
        "tech_stack": [],
        "news": None
    }

    # --- Hiring: Greenhouse (free, no auth) ---
    try:
        slug = company_domain.replace(".com", "").replace(".io", "").replace(".ai", "")
        gh = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=5
        )
        if gh.status_code == 200:
            jobs = gh.json().get("jobs", [])
            signals["hiring_roles"] = [j["title"] for j in jobs[:5]]
            print(f"   ✅ Greenhouse: {len(jobs)} open roles found")
    except Exception as e:
        print(f"   ⚠️  Greenhouse failed: {e}")

    # --- Hiring fallback: Lever (free, no auth) ---
    if not signals["hiring_roles"]:
        try:
            lv = requests.get(
                f"https://api.lever.co/v0/postings/{slug}",
                timeout=5
            )
            if lv.status_code == 200:
                jobs = lv.json()
                signals["hiring_roles"] = [j["text"] for j in jobs[:5]]
                print(f"   ✅ Lever: {len(jobs)} open roles found")
        except Exception as e:
            print(f"   ⚠️  Lever failed: {e}")

    # --- News + Funding: Tavily (free) ---
    try:
        from tavily import TavilyClient
        tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

        # Funding signal
        funding_res = tavily.search(
            f"{company_name} funding round 2024 OR 2025 OR 2026",
            max_results=2
        )
        if funding_res.get("results"):
            signals["funding"] = funding_res["results"][0]["content"][:300]
            print(f"   ✅ Tavily funding signal found")

        # News signal
        news_res = tavily.search(
            f"{company_name} growth expansion announcement 2025",
            max_results=2
        )
        if news_res.get("results"):
            signals["news"] = news_res["results"][0]["content"][:300]
            print(f"   ✅ Tavily news signal found")

    except Exception as e:
        print(f"   ⚠️  Tavily failed: {e}")

    # --- Tech Stack: BuiltWith (free key) ---
    try:
        bw = requests.get(
            f"https://api.builtwith.com/free1/api.json?KEY=free&LOOKUP={company_domain}",
            timeout=5
        )
        if bw.status_code == 200:
            data = bw.json()
            techs = data.get("Results", [{}])[0].get("Result", {}).get("Paths", [{}])[0].get("Technologies", [])
            signals["tech_stack"] = [t["Name"] for t in techs[:5]]
            print(f"   ✅ BuiltWith: {signals['tech_stack']}")
    except Exception as e:
        print(f"   ⚠️  BuiltWith failed: {e}")

    print(f"\n   📦 Signals collected: {json.dumps(signals, indent=2)}")
    return signals


# ─── TOOL 2: Research Analyst ──────────────────────────────
def tool_research_analyst(
    company_name: str,
    signals_json: str,
    icp_description: str
) -> dict:
    print(f"\n🧠 [Stage 2] Running Research Analyst for {company_name}...")

    prompt = f"""You are a senior GTM analyst at a top-tier sales intelligence firm.

SIGNALS JSON:
{signals_json}

SELLER ICP:
{icp_description}

OUTPUT FORMAT — respond ONLY in this exact JSON schema, no preamble:
{{
  "p1": "1 paragraph company growth moment, citing 2 specific signals",
  "p2": "1 paragraph ICP alignment, citing 1 signal",
  "pain_points": ["specific pain 1", "specific pain 2"],
  "signal_citations": ["signal_key1", "signal_key2"]
}}

RULES (non-negotiable):
1. Every factual claim in p1/p2 must come from the signals JSON above.
2. Never invent funding amounts, headcounts, or tool names not in the signals.
3. If a signal key has value null or empty, do not reference that signal.
4. Be specific — mention actual role titles from hiring_roles if available.
"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"}
    )

    raw = response.choices[0].message.content
    brief = json.loads(raw)
    print(f"   ✅ Brief generated")
    print(f"   📝 P1: {brief['p1'][:100]}...")
    return brief


# ─── TOOL 3: Outreach Sender ───────────────────────────────
def tool_outreach_automated_sender(
    recipient_email: str,
    recipient_name: str,
    account_brief_json: str,
    sender_icp: str,
    tone: str = "consultative"
) -> dict:
    print(f"\n📧 [Stage 3] Composing + Sending email to {recipient_email}...")

    # --- Compose email via Groq ---
    compose_prompt = f"""You are an expert B2B sales writer. Write a cold outreach email.

ACCOUNT BRIEF:
{account_brief_json}

SENDER ICP: {sender_icp}
RECIPIENT NAME: {recipient_name}
TONE: {tone}

RULES (Zero-Template Policy):
- Sentence 1: Open with a SPECIFIC signal (e.g., a funding round or specific job role)
- Body: Connect 2 signals to a concrete security/operational risk
- CTA: ONE ask only — a 15-minute call or free risk assessment
- Max 180 words. NO generic openers like "Hope this finds you well"
- NO bullet points in the email body
- Subject line must be specific, not generic

Respond in JSON:
{{
  "subject": "email subject line",
  "body": "full email body text"
}}
"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": compose_prompt}],
        temperature=0.6,
        response_format={"type": "json_object"}
    )

    email_data = json.loads(response.choices[0].message.content)

    # --- Lint the email ---
    CLICHE_PATTERNS = [
        r"hope this finds you",
        r"i wanted to reach out",
        r"touching base",
        r"circling back",
        r"synergy"
    ]
    word_count = len(email_data["body"].split())
    issues = []
    if word_count > 200:
        issues.append(f"Too long: {word_count} words (max 200)")
    for pattern in CLICHE_PATTERNS:
        if re.search(pattern, email_data["body"], re.IGNORECASE):
            issues.append(f"Cliché detected: {pattern}")

    if issues:
        print(f"   ⚠️  Linting issues: {issues} — retrying...")
        compose_prompt += f"\n\nPREVIOUS ATTEMPT FAILED THESE CHECKS: {issues}\nFix all issues in your next attempt."
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": compose_prompt}],
            temperature=0.5,
            response_format={"type": "json_object"}
        )
        email_data = json.loads(response.choices[0].message.content)

    print(f"   ✅ Email composed: '{email_data['subject']}'")
    print(f"   📨 Body preview: {email_data['body'][:150]}...")

    # --- Send via Resend ---
    result = resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": recipient_email,
        "subject": email_data["subject"],
        "html": f"<p>{email_data['body'].replace(chr(10), '<br>')}</p>"
    })

    print(f"\n   ✅ EMAIL SENT! Message ID: {result['id']}")
    return {
        "message_id": result["id"],
        "subject": email_data["subject"],
        "body": email_data["body"],
        "status": "sent"
    }


# ─── MAIN AGENT LOOP ───────────────────────────────────────
def run_firereach(
    company_name: str,
    company_domain: str,
    icp: str,
    recipient_email: str,
    recipient_name: str = "Hiring Manager"
):
    print(f"\n🔥 FireReach Agent Starting...")
    print(f"   Target: {company_name} ({company_domain})")
    print(f"   ICP: {icp[:80]}...")
    print("=" * 60)

    # Stage 1 — Signal Harvesting
    signals = tool_signal_harvester(company_name, company_domain)

    # Stage 2 — Research Analyst
    brief = tool_research_analyst(
        company_name=company_name,
        signals_json=json.dumps(signals),
        icp_description=icp
    )

    # Stage 3 — Compose + Send
    result = tool_outreach_automated_sender(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        account_brief_json=json.dumps(brief),
        sender_icp=icp,
        tone="consultative"
    )

    print("\n" + "=" * 60)
    print("🎉 FireReach Complete!")
    print(f"   ✅ Email sent to: {recipient_email}")
    print(f"   📧 Subject: {result['subject']}")
    print(f"   🆔 Message ID: {result['message_id']}")
    print("\n📧 FULL EMAIL SENT:")
    print("-" * 40)
    print(result["body"])
    return result


# ─── RUN IT ────────────────────────────────────────────────
if __name__ == "__main__":
    run_firereach(
        company_name="Stripe",
        company_domain="stripe.com",
        icp="We sell high-end cybersecurity training to Series B+ startups. Our ICP is CTOs and security engineers at fast-growing tech companies concerned about compliance and infrastructure security as headcount scales.",
        recipient_email="adikasareprojects@gmail.com",  # 👈 your own email for testing
        recipient_name="Aryan"
    )
