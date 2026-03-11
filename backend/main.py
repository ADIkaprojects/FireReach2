"""
FireReach — FastAPI Application

Endpoints:
  POST /run-outreach    → enqueues agent as BackgroundTask, returns job_id instantly
  GET  /status/{job_id} → polls Supabase for latest agent state
  GET  /stream/{job_id} → SSE async generator, pushes Supabase events to frontend
  GET  /health          → health check

Architecture:
  • BackgroundTasks (built-in FastAPI) avoids Vercel 10s timeout
  • SSE generator polls Supabase every 500ms — no WebSocket needed
  • All sensitive config via environment variables (Render / Vercel env vars)
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
from uuid import uuid4

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from models import AgentState, JobCreatedResponse, OutreachRequest
from agent.loop import run_agent
from agent.supabase_client import get_supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("firereach")

app = FastAPI(title="FireReach API", version="2.0.0")

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Restrict to the deployed frontend domain in production.
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,https://firereach.vercel.app",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Background Task ─────────────────────────────────────────────────────────

async def run_agent_task(job_id: str, req: OutreachRequest) -> None:
    """Runs the full agent pipeline in the background."""
    state = AgentState(
        job_id=job_id,
        company_name=req.company_name,
        company_domain=req.company_domain,
        icp_description=req.icp_description,
        tone=req.tone,
        status="running",
    )
    try:
        final_state = await run_agent(state)
        # Persist final state summary
        sb = get_supabase()
        sb.table("jobs").update({
            "status": final_state.status,
            "icp_score": final_state.icp_score,
            "icp_label": final_state.icp_label,
            "error_message": final_state.error_message,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }).eq("job_id", job_id).execute()
    except Exception as exc:
        logger.exception("Agent task failed for job %s: %s", job_id, exc)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/run-outreach", response_model=JobCreatedResponse, status_code=202)
async def run_outreach(req: OutreachRequest, background: BackgroundTasks) -> JobCreatedResponse:
    """
    Accepts an outreach request, creates a job record, and fires the agent
    as a background task. Returns job_id immediately (no timeout risk).
    """
    job_id = str(uuid4())

    try:
        sb = get_supabase()
        sb.table("jobs").insert({
            "job_id": job_id,
            "company_name": req.company_name,
            "company_domain": req.company_domain,
            "status": "queued",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        logger.warning("Could not persist job to Supabase: %s", exc)

    background.add_task(run_agent_task, job_id, req)
    return JobCreatedResponse(job_id=job_id)


@app.get("/status/{job_id}")
async def get_status(job_id: str) -> dict:
    """
    Polling endpoint — returns the latest status and events for a job.
    Used by the frontend when SSE is unavailable.
    """
    _validate_job_id(job_id)
    try:
        sb = get_supabase()
        job = sb.table("jobs").select("*").eq("job_id", job_id).single().execute()
        events = (
            sb.table("agent_events")
            .select("*")
            .eq("job_id", job_id)
            .order("timestamp", desc=False)
            .execute()
        )
        return {"job": job.data, "events": events.data}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}") from exc


@app.get("/stream/{job_id}")
async def stream_job(job_id: str) -> StreamingResponse:
    """
    SSE endpoint — streams progress events to the frontend as they're written
    to Supabase by the background agent task.
    """
    _validate_job_id(job_id)

    async def event_generator():
        last_seen_id: int | None = None
        consecutive_empty = 0

        while True:
            try:
                sb = get_supabase()
                query = (
                    sb.table("agent_events")
                    .select("*")
                    .eq("job_id", job_id)
                    .order("id", desc=False)
                )
                if last_seen_id is not None:
                    query = query.gt("id", last_seen_id)

                result = query.execute()
                rows = result.data or []

                if rows:
                    consecutive_empty = 0
                    for row in rows:
                        last_seen_id = row["id"]
                        yield f"data: {json.dumps(row)}\n\n"
                        if row.get("status") in ("done", "error"):
                            return
                else:
                    consecutive_empty += 1
                    # Timeout after 5 minutes of no events (600 × 0.5s)
                    if consecutive_empty > 600:
                        yield f'data: {json.dumps({"status": "error", "message": "timeout"})}\n\n'
                        return

            except Exception as exc:
                logger.warning("SSE poll error for job %s: %s", job_id, exc)

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}


# ─── Input Validation Helpers ─────────────────────────────────────────────────

def _validate_job_id(job_id: str) -> None:
    """
    Validate that job_id is a UUID to prevent path injection attacks.
    Raises 400 for invalid formats.
    """
    import re
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    if not re.match(uuid_pattern, job_id, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Invalid job_id format")
