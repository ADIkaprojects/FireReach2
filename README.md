# 🔥 FireReach — Autonomous Outreach Engine

> **Total Monthly Cost: ₹0** — Every tool is free-tier or open-source.

FireReach is a 4-stage autonomous agent pipeline that eliminates the manual signal-to-outreach loop:

1. **Signal Harvester** — Fetches live funding, hiring, tech-stack & news signals (Tavily + Greenhouse/Lever + BuiltWith)
2. **Contact Resolver** — Resolves `company.com → { name, title, verified_email }` (Hunter.io domain search → Snov.io SMTP verify)
3. **Research Analyst** — LLM synthesises signals into a grounded Account Brief (Groq Llama 3.3 70B)
4. **Outreach Sender** — Composes, quality-gates (multi-agent critic), and dispatches the email (Resend.com)

---

## Architecture

```
Next.js Frontend (Vercel)
       │ SSE + REST
FastAPI Backend (Render)
  ├── POST /run-outreach  →  BackgroundTask  →  ReAct Loop
  ├── GET  /stream/:id    →  SSE async generator
  └── GET  /status/:id   →  polling fallback
       │
  ┌────┴────────────────────────────────────┐
  │          Pydantic AgentState           │
  │  Stage1 → Stage2 → Stage3 → Stage4    │
  └───────────────────────────────────────┘
       │                          │
  Free APIs               Supabase (events + log)
  Groq / Gemini           Resend.com
```

---

## API Changes & Fixes (Build Notes)

### Serper.dev → Replaced by Tavily
The original blueprint used Serper.dev for funding news and Greenhouse slug discovery.
Serper requires a paid key beyond the trial and returns 403 on the free tier.

**Fix:** All Serper calls replaced with Tavily:
- Funding signal: `Tavily.search("{company} funding round Series 2024 2025")`
- News signal: already used Tavily — unchanged
- Greenhouse slug: now tries direct slug patterns (`retool`, `retool-app`) without any search fallback

```python
# Before (broken on free tier)
data = await _serper_search(client, f'"{company}" funding site:techcrunch.com')

# After (working)
data = await _tavily_search(client, f"{company} funding round Series investment 2024 2025")
```

### Apollo / PDL → Replaced by Hunter.io
The original blueprint used Apollo.io (people search) as the primary contact finder, with Hunter.io only for email resolution after Apollo found a name. Apollo's free tier does not return emails and its people search is unreliable without a paid key.

**Fix:** Removed Apollo entirely. Hunter.io Domain Search returns **name + title + email in a single call**:

```python
GET https://api.hunter.io/v2/domain-search?domain=retool.com&api_key=...
# Returns: first_name, last_name, position, email, confidence score
```

The resolver picks the most senior contact (CTO → VP Engineering → CISO → Head of Security order), then SMTP-verifies via Snov.io.

### Relative imports → Absolute imports
Running `uvicorn main:app` from inside `backend/` caused `ImportError: attempted relative import with no known parent package` because Python didn't treat the directory as a package.

**Fix:** All `from .models import ...` / `from ..tools import ...` replaced with absolute imports (`from models import ...`, `from agent.tools.llm_client import ...`).

### Supabase upsert → update
On job completion, the agent was calling `upsert()` which tried to insert a new row — failing with `null value in column "company_name" violates not-null constraint` because the upsert payload only included status fields.

**Fix:** Changed to `update().eq("job_id", job_id)` — the row already exists from job creation, so only the changed fields are written.

### Next.js upgrade (security)
Next.js 14 had a high-severity DoS CVE. Upgraded to Next.js 15.2.4 + React 19.

### TypeScript `unknown` not assignable to `ReactNode`
React 19 / TypeScript 5.x correctly rejects rendering `unknown` values from `Record<string, unknown>` in JSX. All `&&`-guarded JSX blocks replaced with explicit ternaries (`condition ? <JSX /> : null`) to force the type to `JSX.Element | null`.

### Test email override
When using Resend's `onboarding@resend.dev` sender (no domain required), emails can only be delivered to the Resend account owner's email. Added `TEST_TO_EMAIL` env var to override the recipient during local testing.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Free accounts on: Groq, Gemini (Google AI Studio), Tavily, Hunter.io, Snov.io, Resend.com, Supabase

### 1. Clone & configure

```bash
git clone https://github.com/ADIkaprojects/FireReach
cd FireReach
cp .env.example backend/.env
# Fill in your API keys in backend/.env
```

### 2. Supabase setup

Open `docs/supabase_schema.sql` and run it in your Supabase SQL editor.

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### 5. N8N automation layer (optional)

```bash
docker run -it --rm -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
# Open http://localhost:5678, import n8n/workflow-export.json
```

---

## Deploy to Render + Vercel (one-click)

1. Push to GitHub
2. Connect repo to [Render.com](https://render.com) — `render.yaml` auto-configures both services
3. Add env vars in Render dashboard (see `.env.example`)
4. Connect `frontend/` to [Vercel](https://vercel.com) — auto-detected as Next.js
5. Set `NEXT_PUBLIC_API_URL` to your Render backend URL in Vercel env vars

---

## Project Structure

```
firereach/
├── backend/
│   ├── main.py                  # FastAPI app, SSE endpoints
│   ├── models.py                # Pydantic schemas for all stages
│   ├── validators.py            # Citation checker, email linter, injection sanitiser
│   └── agent/
│       ├── loop.py              # ReAct agent loop (Pydantic state)
│       ├── prompts.py           # All LLM system prompts
│       ├── supabase_client.py   # Singleton Supabase client
│       └── tools/
│           ├── llm_client.py         # Groq + Gemini with retry/fallback
│           ├── signal_harvester.py   # Stage 1 — Tavily + Greenhouse + Lever + BuiltWith
│           ├── contact_resolver.py   # Stage 2 — Hunter.io → Snov.io
│           ├── research_analyst.py   # Stage 3 — LLM grounded brief
│           └── outreach_sender.py    # Stage 4 — compose + dispatch
├── frontend/
│   ├── app/
│   │   ├── layout.tsx           # Next.js root layout
│   │   ├── page.tsx             # ICP form + live agent stream UI
│   │   └── globals.css          # Tailwind imports
│   └── hooks/
│       └── useAgentStream.ts    # SSE consumer hook
├── n8n/
│   ├── Dockerfile               # Self-hosted N8N
│   └── workflow-export.json     # Import into N8N to activate SDR automation
├── docs/
│   ├── architecture.mmd         # Mermaid sequence diagram (full pipeline)
│   └── supabase_schema.sql      # Run once in Supabase SQL editor
├── DOCS.md                      # Technical documentation
├── README.md                    # This file
├── render.yaml                  # One-click Render.com deployment
└── .env.example                 # All required environment variables documented
```

---

## Free Stack

| Component | Tool | Free Limit |
|---|---|---|
| LLM (Primary) | Groq — Llama 3.3 70B | 14,400 req/day |
| LLM (Fallback) | Google Gemini 1.5 Flash | 1,500 req/day |
| Signal — Funding + News | Tavily API | 1,000 searches/mo |
| Signal — Hiring | Greenhouse API + Lever API | Unlimited, no auth |
| Signal — Tech Stack | BuiltWith free key | Free tier |
| Contact — Name/Title/Email | Hunter.io Domain Search | 25 searches/mo |
| Contact — SMTP Verify | Snov.io free | 50 credits/mo |
| Email Send | Resend.com | 3,000 emails/mo |
| Database | Supabase free tier | 500MB Postgres |
| Backend | Render.com free tier | Always-on web service |
| Frontend | Vercel free tier | Unlimited deploys |
| Automation | N8N self-hosted | Free forever |

---

*FireReach v2.0 — March 2026*


---

## Architecture

```
Next.js Frontend (Vercel)
       │ SSE + REST
FastAPI Backend (Render)
  ├── POST /run-outreach  →  BackgroundTask  →  ReAct Loop
  ├── GET  /stream/:id    →  SSE async generator
  └── GET  /status/:id   →  polling fallback
       │
  ┌────┴────────────────────────────────────┐
  │          Pydantic AgentState           │
  │  Stage1 → Stage2 → Stage3 → Stage4    │
  └───────────────────────────────────────┘
       │                          │
  Free APIs               Supabase (events + log)
  Groq / Gemini           Resend.com
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free account on: Groq, Gemini (Google AI Studio), Serper.dev, Tavily, Apollo.io, Hunter.io, Resend.com, Supabase

### 1. Clone & configure

```bash
git clone https://github.com/yourorg/firereach
cd firereach
cp .env.example .env
# Fill in your API keys in .env
```

### 2. Supabase setup

Open `docs/supabase_schema.sql` and run it in your Supabase SQL editor to create the required tables.

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### 5. N8N automation layer (optional)

```bash
# Local Docker — zero setup, no account needed
docker run -it --rm -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
# Open http://localhost:5678
# Import n8n/workflow-export.json via Settings → Import Workflow
```

---

## Deploy to Render + Vercel (one-click)

1. Push to GitHub
2. Connect repo to [Render.com](https://render.com) — `render.yaml` auto-configures both services
3. Add env vars in Render dashboard (see `.env.example`)
4. Connect `frontend/` to [Vercel](https://vercel.com) — auto-detected as Next.js
5. Set `NEXT_PUBLIC_API_URL` to your Render backend URL in Vercel env vars

---

## Project Structure

```
firereach/
├── backend/
│   ├── main.py                  # FastAPI app, SSE endpoints
│   ├── models.py                # Pydantic schemas for all stages
│   ├── validators.py            # Citation checker, email linter, injection sanitiser
│   └── agent/
│       ├── loop.py              # ReAct agent loop (Pydantic state)
│       ├── prompts.py           # All LLM system prompts
│       ├── supabase_client.py   # Singleton Supabase client
│       └── tools/
│           ├── llm_client.py         # Groq + Gemini with retry/fallback
│           ├── signal_harvester.py   # Stage 1 — deterministic signals
│           ├── contact_resolver.py   # Stage 2 — contact waterfall
│           ├── research_analyst.py   # Stage 3 — LLM grounded brief
│           └── outreach_sender.py    # Stage 4 — compose + dispatch
├── frontend/
│   ├── app/
│   │   ├── layout.tsx           # Next.js root layout
│   │   ├── page.tsx             # ICP form + live agent stream UI
│   │   └── globals.css          # Tailwind imports
│   └── hooks/
│       └── useAgentStream.ts    # SSE consumer hook
├── n8n/
│   ├── Dockerfile               # Self-hosted N8N
│   └── workflow-export.json     # Import into N8N to activate SDR automation
├── docs/
│   ├── architecture.mmd         # Mermaid sequence diagram (full pipeline)
│   └── supabase_schema.sql      # Run once in Supabase SQL editor
├── DOCS.md                      # Technical documentation (evaluation deliverable)
├── README.md                    # This file
├── render.yaml                  # One-click Render.com deployment
└── .env.example                 # All required environment variables documented
```

---

## Free Stack

| Component | Tool | Free Limit |
|---|---|---|
| LLM (Primary) | Groq — Llama 3.3 70B | 14,400 req/day |
| LLM (Fallback) | Google Gemini 1.5 Flash | 1,500 req/day |
| Signal — Funding | Serper.dev | 2,500 searches/mo |
| Signal — Hiring | Greenhouse API + Lever API | Unlimited, no auth |
| Signal — Tech Stack | BuiltWith free key | Free tier |
| Signal — News | Tavily API | 1,000 searches/mo |
| Contact — Name/Title | Apollo.io free tier | Unlimited views |
| Contact — Email | Hunter.io free tier | 25 searches/mo |
| Contact — Verify | Snov.io free | 50 credits/mo |
| Email Send | Resend.com | 3,000 emails/mo |
| Database | Supabase free tier | 500MB Postgres |
| Backend | Render.com free tier | Always-on web service |
| Frontend | Vercel free tier | Unlimited deploys |
| Automation | N8N self-hosted | Free forever |

---

*FireReach v2.0 — Rabbitt AI — March 2026*
