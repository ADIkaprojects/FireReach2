# 🔥 FireReach — Autonomous Outreach Engine

> **Total Monthly Cost: ₹0** — Every tool is free-tier or open-source.

FireReach is a 4-stage autonomous agent pipeline that eliminates the manual signal-to-outreach loop:

1. **Signal Harvester** — Fetches live funding, hiring, tech-stack & news signals (Serper + Greenhouse/Lever + BuiltWith + Tavily)
2. **Contact Resolver** — Resolves `company.com → { name, title, verified_email }` (Apollo → Hunter → Snov.io waterfall)
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
