"""
FireReach — ReAct Agent Loop (Pydantic State)

Orchestrates the 4-stage pipeline:
  Stage 1 → tool_signal_harvester
  Stage 2 → tool_contact_resolver
  Stage 3 → tool_research_analyst
  Stage 4 → tool_outreach_automated_sender

State is Pydantic-validated at every stage boundary.
Progress events are written to Supabase for SSE streaming.
Tool call deduplication prevents infinite loops.
"""

from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone

from models import AgentState, SignalResult, ContactResult, AccountBrief, SendResult
from agent.supabase_client import get_supabase
from agent.tools.signal_harvester import run_signal_harvester
from agent.tools.contact_resolver import run_contact_resolver
from agent.tools.research_analyst import run_research_analyst
from agent.tools.outreach_sender import run_outreach_sender


MAX_ITERATIONS = 10


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _tool_call_hash(tool_name: str, kwargs: dict) -> str:
    payload = json.dumps({"tool": tool_name, "args": kwargs}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def _emit_event(
    job_id: str,
    stage: str,
    message: str,
    status: str,
    data: dict | None = None,
) -> None:
    """
    Writes a progress event to Supabase.
    The SSE endpoint polls this table and pushes events to the frontend.
    """
    try:
        sb = get_supabase()
        sb.table("agent_events").insert({
            "job_id": job_id,
            "stage": stage,
            "message": message,
            "status": status,
            "data": data or {},
            "timestamp": _now_iso(),
        }).execute()
    except Exception:
        pass   # event emission must never block the pipeline


async def _score_icp(signals: SignalResult) -> tuple[int, str]:
    """Score how well signals match the ideal customer profile."""
    score = 0
    if signals.funding and signals.funding.round:
        if "series b" in (signals.funding.round or "").lower():
            score += 4
        elif signals.funding.round:
            score += 2
    if len(signals.hiring_roles) >= 3:
        score += 3
    elif signals.hiring_roles:
        score += 1
    if signals.tech_stack:
        security_tools = {
            "okta", "cloudflare", "datadog", "crowdstrike", "pagerduty",
            "sentry", "snyk", "hashicorp vault", "wiz", "lacework",
        }
        if any(t.lower() in security_tools for t in signals.tech_stack):
            score += 2
    if signals.news and signals.news.headline:
        score += 1

    label = "High Fit" if score >= 8 else "Good Fit" if score >= 5 else "Low Fit"
    return score, label


async def run_agent(state: AgentState) -> AgentState:
    """
    Main ReAct loop. Executes all four stages deterministically.
    Writes SSE progress events after each stage.
    Returns the final AgentState.
    """
    state.status = "running"
    seen_calls: set[str] = set()

    await _emit_event(
        state.job_id, "init",
        f"Starting FireReach for {state.company_name}",
        "running",
    )

    try:
        # ── STAGE 1: Signal Harvester ────────────────────────────────────────
        call_hash = _tool_call_hash("signal_harvester", {
            "company_name": state.company_name,
            "company_domain": state.company_domain,
        })
        if call_hash not in seen_calls:
            seen_calls.add(call_hash)
            await _emit_event(
                state.job_id, "stage_1",
                f"Harvesting live signals for {state.company_name}…",
                "running",
            )
            signals = await run_signal_harvester(
                company_name=state.company_name,
                company_domain=state.company_domain,
            )
            state.signals = signals
            state.iteration += 1

            icp_score, icp_label = await _score_icp(signals)
            state.icp_score = icp_score
            state.icp_label = icp_label

            await _emit_event(
                state.job_id, "stage_1",
                f"Signals harvested · ICP Score: {icp_score}/10 — {icp_label}",
                "running",
                {
                    "funding": signals.funding.model_dump() if signals.funding else None,
                    "hiring_count": len(signals.hiring_roles),
                    "tech_stack": signals.tech_stack,
                    "icp_score": icp_score,
                    "icp_label": icp_label,
                },
            )

        # ── STAGE 2: Contact Resolver ────────────────────────────────────────
        call_hash = _tool_call_hash("contact_resolver", {
            "company_domain": state.company_domain,
        })
        if call_hash not in seen_calls:
            seen_calls.add(call_hash)
            await _emit_event(
                state.job_id, "stage_2",
                f"Resolving decision-maker contact for {state.company_domain}…",
                "running",
            )
            contact = await run_contact_resolver(
                company_domain=state.company_domain,
            )
            state.contact = contact
            state.iteration += 1

            if not contact.found:
                await _emit_event(
                    state.job_id, "stage_2",
                    f"Contact not found: {contact.reason}",
                    "done",
                    {"contact": contact.model_dump()},
                )
                state.status = "done"
                state.email_result = SendResult(status="contact_not_found")
                return state

            await _emit_event(
                state.job_id, "stage_2",
                f"Contact resolved: {contact.name} ({contact.title}) · confidence {contact.confidence:.0%}",
                "running",
                {
                    "name": contact.name,
                    "title": contact.title,
                    "source": contact.source,
                    "confidence": contact.confidence,
                    "smtp_verified": contact.smtp_verified,
                },
            )

        # ── STAGE 3: Research Analyst ────────────────────────────────────────
        call_hash = _tool_call_hash("research_analyst", {
            "company_name": state.company_name,
        })
        if call_hash not in seen_calls:
            seen_calls.add(call_hash)
            await _emit_event(
                state.job_id, "stage_3",
                "Synthesising signals into Account Brief…",
                "running",
            )
            brief = await run_research_analyst(
                company_name=state.company_name,
                signals=state.signals,
                contact=state.contact,
                icp_description=state.icp_description,
            )
            state.brief = brief
            state.iteration += 1

            await _emit_event(
                state.job_id, "stage_3",
                "Account Brief ready",
                "running",
                {
                    "p1_preview": brief.p1[:150] + "…" if len(brief.p1) > 150 else brief.p1,
                    "pain_points": brief.pain_points,
                    "signal_citations": brief.signal_citations,
                },
            )

        # ── STAGE 4: Outreach Sender ─────────────────────────────────────────
        call_hash = _tool_call_hash("outreach_sender", {
            "recipient_email": state.contact.email,
        })
        if call_hash not in seen_calls:
            seen_calls.add(call_hash)
            await _emit_event(
                state.job_id, "stage_4",
                f"Composing and dispatching email to {state.contact.name}…",
                "running",
            )
            send_result = await run_outreach_sender(
                contact=state.contact,
                brief=state.brief,
                icp_description=state.icp_description,
                tone=state.tone,
            )
            state.email_result = send_result
            state.iteration += 1

            if send_result.status == "sent":
                await _emit_event(
                    state.job_id, "stage_4",
                    f"Email sent ✓ · Quality Score: {send_result.quality_score:.1f}/10",
                    "done",
                    {
                        "message_id": send_result.message_id,
                        "email_preview": send_result.email_preview,
                        "quality_score": send_result.quality_score,
                    },
                )
            else:
                await _emit_event(
                    state.job_id, "stage_4",
                    f"Send result: {send_result.status}",
                    "done",
                    {"status": send_result.status, "error": send_result.error},
                )

        state.status = "done"

    except Exception as exc:
        state.status = "error"
        state.error_message = str(exc)
        await _emit_event(
            state.job_id, "error",
            f"Agent error: {exc}",
            "error",
            {"error": str(exc)},
        )

    return state
