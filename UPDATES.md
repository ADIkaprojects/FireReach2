# 🔥 FireReach — UPDATES.md v3.0
> **Complete Audit · Missing Features · Bug Fixes · UI Revamp**  
> March 2026 | Based on Whiteboard Session + README Codebase Review

---

## Table of Contents
1. [Whiteboard vs Codebase Analysis](#section-1)
2. [Feature Updates to Build](#section-2)
3. [Code Audit — Working vs Broken](#section-3)
4. [Web Application UI Revamp](#section-4)
5. [Execution Plan (Priority Order)](#section-5)
6. [Complete .env.example (Updated)](#section-6)
7. [Quick Reference Summary](#section-7)

---

<a name="section-1"></a>
## SECTION 1 — Whiteboard vs Codebase Analysis

### 1.1 What the Whiteboard Shows (Full Reading)

The whiteboard defines FireReach as an **Autonomous Outreach Engine** with the following inputs and flow:

| Input | Description |
|---|---|
| **Target Company** | A specific company name the user wants to reach |
| **ICP (Ideal Customer Profile)** | Kis type ki company ko target karna hai / What do we provide |
| **Output** | Mail — a personalized, signal-backed cold email sent to the right contact |

**FireReach can be deployed as:**
- Web Extension (browser plugin)
- Script (CLI / automation)
- Application — Mobile / Web
- Software (standalone)

**The whiteboard defines 6 Signal Types (S1–S6):**
- **S1** — Hiring / Recruitment signals (open roles, headcount growth)
- **S2** — Funding signals (Series A/B/C, investment rounds)
- **S3** — Security requirements (compliance, SOC2, GDPR, security hiring)
- **S4** — Sales signals (new deals, partnerships, revenue mentions)
- **S5** — Hardware need signals
- **S6** — Market / Lead signals

**Signal Verification flow (whiteboard right panel):**
- Type of Service we provide + Company Name → Signal Verification
- Verification checks: capabilities, benchmarks, warranty price, success rate
- Final output is always → **Mail**

**Contact sources mentioned on whiteboard:**
- LinkedIn PeopleList
- X (Twitter)
- Tavily, Serper, Hunter.io
- **Apollo.io Extension** (mentioned separately, underlined — considered critical)

**Multi-model architecture (whiteboard top center):**
- M1, M2, M3, M4 nodes shown — model routing / multi-agent architecture
- One model is crossed out (X) — deprecation or failure mode handling

---

### 1.2 Implemented vs Missing — Full Status Table

| Component / Feature | Current Status | Action Required |
|---|---|---|
| ICP Input Form | ⚠️ Partial | Form exists but captures only company name. Needs industry, size, stage, pain points, geography fields. |
| Target Company Input | ✅ Working | Company name input flows into pipeline correctly. |
| Signal S1 — Hiring | ✅ Working | Greenhouse + Lever APIs active and pulling job postings. |
| Signal S2 — Funding | ✅ Working | Tavily funding search active. Works on free tier. |
| Signal S3 — Security | ❌ Missing | No security/compliance signal harvesting implemented anywhere. |
| Signal S4 — Sales/Deals | ❌ Missing | No sales signal. No partnership or deal-tracking source. |
| Signal S5 — Hardware Need | ❌ Missing | Not implemented. Low priority unless product is hardware-related. |
| Signal S6 — Market/Lead | ❌ Missing | No market signal. NewsAPI or Reddit not integrated. |
| Signal Verification / ICP Scoring | ❌ Missing | No numeric scoring. No ICP-vs-signal matching. Every company gets outreach regardless of fit. |
| Contact — Hunter.io | ✅ Working | Domain search working. Returns name + title + email in one call. |
| Contact — Snov.io Verify | ⚠️ Partial | SMTP verify implemented but only 50 credits/mo free. Needs fallback. |
| Contact — LinkedIn | ❌ Missing | Whiteboard mentions LinkedIn PeopleList — not implemented. |
| Contact — Apollo.io Extension | ❌ Missing | Whiteboard specifically calls this out — not integrated. |
| Contact — X (Twitter) | ❌ Missing | Whiteboard mentions X as a contact source — not implemented. |
| LLM — Groq Primary | ✅ Working | Groq Llama 3.3 70B active with retry logic. |
| LLM — Gemini Fallback | ✅ Working | Gemini 1.5 Flash fallback implemented. |
| Multi-Model Routing (M1–M4) | ❌ Missing | Whiteboard shows multi-model architecture. Only 2 models, no routing logic. |
| Email Send — Resend.com | ❌ BROKEN | Free tier restricts delivery to owner email only. Must replace with SendGrid. |
| Email Send — SendGrid | ❌ Missing | Not implemented. Must replace Resend.com immediately. |
| Quality Gate / Critic Agent | ⚠️ Partial | Mentioned in README but actual implementation needs verification in code. |
| SSE Live Streaming | ✅ Working | FastAPI SSE endpoint + React hook are both implemented. |
| Supabase Logging | ✅ Working | Job creation, event logging, status update all working after upsert→update fix. |
| N8N Automation Layer | ⚠️ Partial | Workflow JSON exists but not verified functional. Docker setup works. |
| Web Application UI | ⚠️ Poor | Functional but plain. Needs complete visual redesign. |
| Frontend — ICP Form | ⚠️ Partial | Basic form exists. Missing ICP fields, score display, signal breakdown panel. |
| Frontend — Results View | ⚠️ Partial | Shows raw stream. Needs structured output: score card, contact card, email preview. |
| Render Deployment | ✅ Working | render.yaml configured correctly. Backend deploys. |
| Vercel Deployment | ✅ Working | Frontend auto-detected as Next.js. Deploys correctly. |
| Environment Variables | ⚠️ Partial | .env.example exists but missing SendGrid key, Apollo key, NewsAPI key. |
| Absolute Imports Fix | ✅ Fixed | Relative import issue resolved per README build notes. |
| Next.js Security Upgrade | ✅ Fixed | Upgraded to Next.js 15.2.4 + React 19. |

---

<a name="section-2"></a>
## SECTION 2 — Feature Updates to Build

### UPDATE 1 — Replace Resend with SendGrid 🚨 CRITICAL BUG FIX

> **WHY:** Resend.com free tier can ONLY deliver emails to the account owner's verified address. This means FireReach **cannot send outreach to any real prospect**. This is a showstopper. Fix this before anything else.

**What to change:**
- Remove `resend` package from `requirements.txt`
- Install `sendgrid` package
- Replace email dispatch logic in `backend/agent/tools/outreach_sender.py`
- Add `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` to `.env.example`

**Code change in `backend/agent/tools/outreach_sender.py`:**

```python
# ❌ OLD CODE (Resend — broken on free tier)
import resend
resend.api_key = os.getenv("RESEND_API_KEY")
resend.Emails.send({
    "from": "you@yourdomain.com",
    "to": recipient_email,
    "subject": subject,
    "html": body_html
})

# ✅ NEW CODE (SendGrid — works for any recipient)
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

message = Mail(
    from_email=os.getenv("SENDGRID_FROM_EMAIL"),
    to_emails=recipient_email,
    subject=subject,
    html_content=body_html
)
sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
response = sg.send(message)
```

**SendGrid Free Tier advantages over Resend:**
- 100 emails/day FREE forever
- Full delivery to **any** recipient email — no sandbox limitation
- Built-in tracking: opens, clicks, bounces
- Sign up: [sendgrid.com](https://sendgrid.com)

---

### UPDATE 2 — Full ICP Input Form

> **WHY:** Currently the ICP form only takes a company name. The whiteboard clearly defines ICP as "Kis type ki company ko target karna hai + what do we provide." Without a proper ICP definition, there is nothing to match signals against.

**New ICP fields to add to `frontend/app/page.tsx`:**

| Field | Type | Example Values |
|---|---|---|
| Industry / Vertical | Dropdown | SaaS, Fintech, Healthcare, E-commerce |
| Company Size Range | Dropdown | 10–50, 50–200, 200–1000, 1000+ |
| Funding Stage | Dropdown | Bootstrapped, Seed, Series A, Series B, Series C+ |
| Target Geography | Multi-select | US, Europe, India, Global |
| Pain Points / Use Case | Free text | What problem does your product solve |
| Your Product / Service | Free text | What you are offering |
| Target Job Title | Multi-select | CTO, VP Engineering, CISO, Head of Security |

**Backend change — add to `backend/models.py`:**

```python
class ICPProfile(BaseModel):
    industry: str
    size_range: str                   # e.g. "50-200"
    funding_stage: str                # e.g. "Series A"
    geography: list[str]              # e.g. ["US", "Europe"]
    pain_points: str                  # free text
    your_product: str                 # free text
    target_titles: list[str]          # e.g. ["CTO", "VP Engineering"]

class OutreachRequest(BaseModel):
    company_name: str
    icp: ICPProfile                   # NEW — full ICP attached to every job
```

---

### UPDATE 3 — ICP Scoring Engine (Signal Verification System)

> **WHY:** This is the "Signal Verification" box on the whiteboard. Every company should receive a numeric fit score (0–100) before an email is sent. Currently zero scoring exists — every company gets outreach regardless of how poorly it matches the ICP.

**Create new file: `backend/agent/tools/icp_scorer.py`**

**Scoring weights:**

| Signal | Points | Reasoning |
|---|---|---|
| Recent funding (last 90 days) | 25 pts | Has budget right now |
| Hiring in target department | 20 pts | Active pain point |
| Tech stack match with ICP | 15 pts | Product is relevant |
| Company size within ICP range | 15 pts | Right customer profile |
| Industry / vertical match | 10 pts | Core ICP fit |
| News mentions growth/expansion | 10 pts | Scaling = spending |
| Geography match | 5 pts | Reachable market |
| **Total** | **100 pts** | |

**Score tiers:**

| Score | Tier | Action |
|---|---|---|
| 80–100 | 🔥 HOT LEAD | Send email immediately |
| 55–79 | ⚡ WARM LEAD | Send email with nurture tag |
| 30–54 | 🌤 POTENTIAL | Log to Supabase, skip email, revisit in 30 days |
| 0–29 | ❌ POOR FIT | Skip entirely, log reason |

**Gate logic to add in `backend/agent/loop.py`:**

```python
# After Stage 3 completes scoring:
if state.icp_score < 30:
    state.status = "skipped_poor_fit"
    await log_to_supabase(job_id, "Skipped — ICP score too low", state.icp_score)
    return state  # Never reaches Stage 4

elif state.icp_score < 55:
    state.status = "queued_potential"
    await log_to_supabase(job_id, "Queued for 30-day review", state.icp_score)
    return state  # Add to review queue, skip immediate send
```

---

### UPDATE 4 — New Signal Types (S3, S4, S6)

> **WHY:** Whiteboard shows 6 signal types. Only S1 (Hiring) and S2 (Funding) are implemented. S3, S4, and S6 must be added to `signal_harvester.py`.

**S3 — Security / Compliance Signal:**
```python
# Add to signal_harvester.py
async def fetch_security_signal(company: str, client) -> dict:
    results = await _tavily_search(
        client,
        f"{company} SOC2 compliance GDPR security audit hiring 2025"
    )
    # Also check Greenhouse for open security/compliance roles
    security_roles = [r for r in hiring_signals if "security" in r["title"].lower()]
    return {"security_hiring": len(security_roles) > 0, "compliance_mentions": results}
```

**S4 — Sales / Partnership Signal:**
```python
async def fetch_sales_signal(company: str, client) -> dict:
    results = await _tavily_search(
        client,
        f"{company} partnership deal announcement enterprise contract 2025"
    )
    return {"partnership_signals": results}
```

**S6 — Market / Intent Signal:**
```python
# Uses NewsAPI (free — 100 req/day at newsapi.org)
async def fetch_market_signal(company: str, client) -> dict:
    news = await _newsapi_search(company)   # new helper function
    reddit = await _reddit_mention_check(company)  # Reddit API — free
    return {"news_mentions": news, "community_buzz": reddit}
```

---

### UPDATE 5 — Apollo.io Extension Integration

> **WHY:** The whiteboard specifically calls out Apollo.io Extension as a standalone item — underlined, meaning it is considered critical. Apollo enriches contacts with seniority data, LinkedIn URLs, and department info.

**Fallback chain becomes:**
```
Hunter.io Domain Search
    → Apollo.io Enrichment (upgrade contact if higher seniority found)
        → Snov.io SMTP Verify
            → Send
```

**Add to `backend/agent/tools/contact_resolver.py`:**

```python
async def apollo_enrich(name: str, domain: str) -> dict:
    """Enrich a contact with Apollo.io for seniority + LinkedIn URL."""
    url = "https://api.apollo.io/v1/people/match"
    payload = {
        "first_name": name.split()[0],
        "last_name": name.split()[-1],
        "domain": domain,
        "api_key": os.getenv("APOLLO_API_KEY")
    }
    resp = await httpx_client.post(url, json=payload)
    data = resp.json()
    return {
        "seniority": data.get("person", {}).get("seniority"),
        "linkedin_url": data.get("person", {}).get("linkedin_url"),
        "title": data.get("person", {}).get("title"),
        "department": data.get("person", {}).get("departments", [])
    }
```

**Seniority ranking (pick the most senior contact):**
```
C_SUITE > VP > DIRECTOR > MANAGER > SENIOR > ENTRY
```

---

### UPDATE 6 — Multi-Model Routing (M1–M4 Architecture)

> **WHY:** The whiteboard shows a multi-model node diagram (M1, M2, M3, M4) with one crossed out — implying different tasks should route to different models by capability and cost.

**Proposed model routing table:**

| Task | Model | Reason |
|---|---|---|
| Signal summarization (Stage 3 brief) | Groq Llama 3.3 70B | Fast, free, sufficient for summarization |
| ICP scoring verification | Groq Llama 3.3 70B | Fast inference, structured output |
| Email drafting (Stage 4) | Gemini 1.5 Flash | Better creative/persuasive writing |
| Critic / quality gate review | Groq Llama 3.3 70B | Fast second opinion |
| Deep research synthesis (optional) | Gemini 1.5 Pro | Depth for complex accounts (paid) |

**Add to `backend/agent/tools/llm_client.py`:**

```python
MODEL_ROUTING = {
    "summarize":    "llama-3.3-70b-versatile",   # Groq
    "score":        "llama-3.3-70b-versatile",   # Groq
    "draft_email":  "gemini-1.5-flash",           # Gemini
    "critic":       "llama-3.3-70b-versatile",   # Groq
}

async def call(prompt: str, task_type: str = "summarize") -> str:
    model = MODEL_ROUTING.get(task_type, "llama-3.3-70b-versatile")
    # Route to Groq or Gemini based on model name
    if "gemini" in model:
        return await _call_gemini(prompt, model)
    else:
        return await _call_groq(prompt, model)
```

---

<a name="section-3"></a>
## SECTION 3 — Code Audit: Working vs Broken

### 3.1 How to Run the Full Audit

Run these commands from your `backend/` directory **before starting any fixes:**

```bash
# 1. Check main app loads without errors
python -c "import main; print('main.py OK')"

# 2. Check all dependencies are installed and consistent
pip check

# 3. Check each tool file individually
python -c "from agent.tools.signal_harvester import run; print('signal_harvester OK')"
python -c "from agent.tools.contact_resolver import run; print('contact_resolver OK')"
python -c "from agent.tools.research_analyst import run; print('research_analyst OK')"
python -c "from agent.tools.outreach_sender import run; print('outreach_sender OK')"

# 4. Check all env vars are present
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
required = ['GROQ_API_KEY','GEMINI_API_KEY','TAVILY_API_KEY',
            'HUNTER_API_KEY','SENDGRID_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_KEY']
missing = [k for k in required if not os.getenv(k)]
print('Missing keys:', missing if missing else 'None — all good!')
"

# 5. Run tests if they exist
python -m pytest tests/ -v --tb=short 2>&1 | head -60
```

---

### 3.2 File-by-File Status

| File | Status | Notes |
|---|---|---|
| `backend/main.py` | ✅ Working | FastAPI app, SSE, background tasks all functional. No changes needed. |
| `backend/models.py` | ⚠️ Incomplete | Missing `ICPProfile` model. Add new Pydantic fields for full ICP. |
| `backend/validators.py` | ✅ Working | Citation checker, email linter, injection sanitiser all present. |
| `backend/agent/loop.py` | ⚠️ Incomplete | No ICP scoring gate. Stage 4 always runs. Add score threshold check. |
| `backend/agent/prompts.py` | ⚠️ Incomplete | Prompts don't reference ICP fields or signal scores. Must update to use full ICP context. |
| `backend/agent/supabase_client.py` | ✅ Working | Singleton pattern. `update()` fix applied. Works correctly. |
| `backend/agent/tools/llm_client.py` | ✅ Working | Groq + Gemini with retry/fallback. No task routing yet. |
| `backend/agent/tools/signal_harvester.py` | ⚠️ Partial | S1+S2 working. S3/S4/S6 completely missing. |
| `backend/agent/tools/contact_resolver.py` | ⚠️ Partial | Hunter.io + Snov.io working. Apollo, LinkedIn, X not integrated. |
| `backend/agent/tools/research_analyst.py` | ⚠️ Incomplete | Writes brief but no ICP scoring. No fit score output. No red flag detection. |
| `backend/agent/tools/outreach_sender.py` | ❌ BROKEN | Uses Resend.com — cannot deliver to real recipients. Replace with SendGrid immediately. |
| `frontend/app/page.tsx` | ⚠️ Partial | Basic form + SSE stream. Missing ICP fields, score display, email preview. |
| `frontend/app/globals.css` | ⚠️ Poor UI | Minimal Tailwind styles. Needs full dark-theme redesign. |
| `frontend/app/layout.tsx` | ✅ Working | Root layout fine. May need font upgrade for visual redesign. |
| `frontend/hooks/useAgentStream.ts` | ✅ Working | SSE consumer hook is functional. |
| `n8n/workflow-export.json` | ⚠️ Unverified | File exists but actual trigger conditions unverified. Import and test manually. |
| `docs/supabase_schema.sql` | ✅ Working | Schema runs in Supabase SQL editor. Tables created correctly. |
| `render.yaml` | ✅ Working | Render deployment config correct for both services. |
| `.env.example` | ⚠️ Incomplete | Missing `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `APOLLO_API_KEY`, `NEWS_API_KEY`. |

---

<a name="section-4"></a>
## SECTION 4 — Web Application UI Revamp

### 4.1 Design Direction

| Attribute | Decision |
|---|---|
| **Theme** | Dark mode by default |
| **Primary Background** | `#0F172A` (deep navy) |
| **Accent Color** | `#F97316` (electric orange) — "fire" branding |
| **Font — UI** | Inter (Google Fonts) |
| **Font — Code/Email** | JetBrains Mono |
| **Feel** | Mission-control dashboard — user should feel like they're launching an autonomous agent |
| **Animations** | Pulse on active pipeline stages, typewriter effect for live LLM output |

---

### 4.2 Color Palette

| Element | Color |
|---|---|
| Page background | `#0F172A` (deep navy) |
| Card / panel background | `#1E293B` (slate) |
| Primary accent (CTA, active stage) | `#F97316` (orange) |
| Success / complete | `#22C55E` (green) |
| Error / failed | `#EF4444` (red) |
| Warning / partial | `#EAB308` (yellow) |
| Text primary | `#F8FAFC` (near white) |
| Text secondary | `#94A3B8` (slate-400) |
| Border / divider | `#334155` (slate-700) |
| Active stage card glow | `box-shadow: 0 0 20px rgba(249,115,22,0.4)` |

---

### 4.3 Page Layout

**Left Panel (30% width) — ICP Configuration**
- Full ICP form with all new fields (from Update 2)
- Target company input with autocomplete
- "Launch Outreach" button — large, orange, with flame icon 🔥
- Saved ICP profiles (dropdown to load previous from Supabase)

**Right Panel (70% width) — Live Agent Console**
- Pipeline visualization: 4 stage cards (S1 → S2 → S3 → S4)
- Each stage card shows: stage name, tool being used, live streamed output
- Active stage: pulses with orange glow border
- Completed stage: turns green with ✅ checkmark
- Failed stage: turns red with error message

**Bottom Section — Results Panel (appears after pipeline completes)**
- **ICP Score Card:** Circular gauge showing 0–100 score with Hot/Warm/Cold label
- **Contact Card:** Avatar placeholder + name + title + verified email badge
- **Signal Summary:** 3–4 bullets of what signals were found
- **Email Preview:** Full email in styled card with Copy and Resend buttons
- **Audit Log:** Collapsible SSE event timeline with timestamps

---

### 4.4 New Components to Build

| Component | File | Description |
|---|---|---|
| `PipelineStageCard` | `components/PipelineStageCard.tsx` | Animated card for each of the 4 stages with pulse/glow on active |
| `ICPScoreGauge` | `components/ICPScoreGauge.tsx` | Circular SVG gauge (0–100) with tier label (Hot/Warm/Cold/Poor) |
| `ContactCard` | `components/ContactCard.tsx` | Name, title, email, verification badge, LinkedIn icon |
| `SignalSummaryPanel` | `components/SignalSummaryPanel.tsx` | List of signals found with icon per signal type |
| `EmailPreviewCard` | `components/EmailPreviewCard.tsx` | Formatted email with subject + body + Copy button |
| `AuditTimeline` | `components/AuditTimeline.tsx` | Collapsible SSE event log with timestamps |
| `ICPForm` | `components/ICPForm.tsx` | Full ICP form with all fields and validation |
| `LaunchButton` | `components/LaunchButton.tsx` | Large CTA button with loading state and flame animation |

---

<a name="section-5"></a>
## SECTION 5 — Execution Plan (Priority Order)

> Work through phases **in order**. Do not start a later phase until the current one is fully tested.

---

### 🔴 PHASE 1 — Critical Bug Fixes *(~2–3 hours)*
> Nothing works correctly until this is done.

- [ ] **1.1** Replace Resend with SendGrid in `outreach_sender.py`
- [ ] **1.2** Add `SENDGRID_API_KEY` + `SENDGRID_FROM_EMAIL` to `.env.example` and `backend/.env`
- [ ] **1.3** Test by sending a real email to a real address (not owner email)
- [ ] **1.4** Run full code audit commands (Section 3.1) and log all errors
- [ ] **1.5** Fix any import errors or missing dependency errors found

---

### 🟠 PHASE 2 — ICP Foundation *(~4–6 hours)*
> Unlocks the scoring engine and the signal verification flow from the whiteboard.

- [ ] **2.1** Add `ICPProfile` Pydantic model to `backend/models.py`
- [ ] **2.2** Update frontend ICP form with all new fields in `page.tsx`
- [ ] **2.3** Pass ICP data through the entire pipeline (`loop.py` → all tools)
- [ ] **2.4** Update `prompts.py` to reference ICP fields in all LLM prompts
- [ ] **2.5** Test end-to-end with a real ICP + real company

---

### 🟠 PHASE 3 — Scoring Engine *(~3–4 hours)*
> The signal verification system from the whiteboard.

- [ ] **3.1** Create `backend/agent/tools/icp_scorer.py` with full scoring logic
- [ ] **3.2** Integrate scorer into `research_analyst.py` — runs after signal collection
- [ ] **3.3** Add gate check in `loop.py` — skip Stage 4 if score < 30
- [ ] **3.4** Log score to Supabase for every job run
- [ ] **3.5** Surface score in SSE stream so frontend can display it

---

### 🟡 PHASE 4 — New Signal Types *(~3–5 hours)*
> Adds S3 (Security), S4 (Sales), S6 (Market) signals.

- [ ] **4.1** Add NewsAPI integration to `signal_harvester.py` (free — 100 req/day)
- [ ] **4.2** Add security/compliance Tavily queries for S3
- [ ] **4.3** Add partnership/deals Tavily queries for S4
- [ ] **4.4** Add Reddit API mention check for S6
- [ ] **4.5** Wire new signals into ICP scorer weights

---

### 🟡 PHASE 5 — Contact Enrichment *(~4–5 hours)*
> Adds Apollo.io integration. Improves contact quality significantly.

- [ ] **5.1** Add Apollo.io `/v1/people/match` call to `contact_resolver.py`
- [ ] **5.2** Build seniority ranking: `CTO > VP Eng > Director > Manager`
- [ ] **5.3** Add LinkedIn profile URL enrichment if Apollo returns it
- [ ] **5.4** Document `APOLLO_API_KEY` in `.env.example`

---

### 🟡 PHASE 6 — UI Revamp *(~8–12 hours)*
> Full visual redesign of the frontend.

- [ ] **6.1** Set up dark theme in `globals.css` with new color palette
- [ ] **6.2** Install Inter + JetBrains Mono via `next/font`
- [ ] **6.3** Build `PipelineStageCard` with pulse animation
- [ ] **6.4** Build `ICPScoreGauge` with circular SVG gauge
- [ ] **6.5** Build `ContactCard`, `SignalSummaryPanel`, `EmailPreviewCard`
- [ ] **6.6** Build `AuditTimeline` from SSE event stream
- [ ] **6.7** Rebuild `page.tsx` layout: left ICP panel + right agent console
- [ ] **6.8** Test on mobile breakpoints and fix responsive layout

---

### 🟢 PHASE 7 — Evals & Testing *(~3–4 hours)*
> The whiteboard mentions EVALS in the top right corner.

- [ ] **7.1** Write eval suite: test pipeline with 5 real company names
- [ ] **7.2** Log: signal quality, contact found Y/N, ICP score, email sent Y/N
- [ ] **7.3** Measure success rate: emails delivered vs bounced vs skipped
- [ ] **7.4** Track which LLM model produced best email quality (A/B log in Supabase)
- [ ] **7.5** Document API rate limits for each service in `DOCS.md`

---

<a name="section-6"></a>
## SECTION 6 — Complete .env.example (Updated)

```bash
# ── LLM ──────────────────────────────────────────────────────
GROQ_API_KEY=                    # console.groq.com — free, 14,400 req/day
GEMINI_API_KEY=                  # aistudio.google.com — free, 1,500 req/day

# ── SIGNALS ──────────────────────────────────────────────────
TAVILY_API_KEY=                  # tavily.com — free, 1,000 searches/mo
BUILTWITH_API_KEY=               # builtwith.com — free tier
NEWS_API_KEY=                    # newsapi.org — free, 100 req/day (NEW — S6 signals)

# ── CONTACTS ─────────────────────────────────────────────────
HUNTER_API_KEY=                  # hunter.io — free, 25 searches/mo
SNOV_CLIENT_ID=                  # app.snov.io — free, 50 credits/mo
SNOV_CLIENT_SECRET=              # app.snov.io — free tier
APOLLO_API_KEY=                  # apollo.io — free tier (NEW — from whiteboard)

# ── EMAIL SEND ───────────────────────────────────────────────
SENDGRID_API_KEY=                # app.sendgrid.com — free, 100 emails/day (NEW — replaces Resend)
SENDGRID_FROM_EMAIL=             # Your verified sender email in SendGrid (NEW)
# RESEND_API_KEY=                # 🗑️ REMOVED — broken on free tier, do not use

# ── DATABASE ─────────────────────────────────────────────────
SUPABASE_URL=                    # Your Supabase project URL
SUPABASE_SERVICE_KEY=            # Supabase service role key (NOT the anon key)

# ── FRONTEND (Vercel) ────────────────────────────────────────
NEXT_PUBLIC_API_URL=             # Your Render backend URL

# ── LOCAL TESTING ────────────────────────────────────────────
# TEST_TO_EMAIL=                 # Optional: override recipient during local dev
```

---

<a name="section-7"></a>
## SECTION 7 — Quick Reference Summary

| What to Do | Priority |
|---|---|
| Replace Resend with SendGrid in `outreach_sender.py` | 🔴 CRITICAL — Do first |
| Run code audit on all 4 tool files | 🔴 CRITICAL — Do first |
| Add full ICP fields to form + models | 🟠 HIGH — Phase 2 |
| Build ICP scoring engine (`icp_scorer.py`) | 🟠 HIGH — Phase 3 |
| Add score gate before Stage 4 email send | 🟠 HIGH — Phase 3 |
| Add S3 Security + S4 Sales + S6 Market signals | 🟡 MEDIUM — Phase 4 |
| Add Apollo.io contact enrichment | 🟡 MEDIUM — Phase 5 |
| Full UI dark-theme redesign | 🟡 MEDIUM — Phase 6 |
| Add all new UI components (Score Gauge, Pipeline Cards etc.) | 🟡 MEDIUM — Phase 6 |
| Write evals suite + Supabase A/B model logging | 🟢 LOWER — Phase 7 |
| Multi-model routing (M1–M4 architecture) | 🟢 LOWER — Phase 7 |

---

### ✅ Definition of Done — FireReach v3.0

FireReach v3.0 is considered **complete** when:

1. A real cold email lands in a real prospect's inbox (not the owner's email)
2. Every email is backed by a scored ICP match (score > 55 to send)
3. The UI shows the pipeline running live with scores and contact details
4. All 6 signal types (S1–S6) are harvested and contribute to the score
5. Evals show >80% contact resolution rate across 10 test companies

---

*FireReach v3.0 — March 2026*
