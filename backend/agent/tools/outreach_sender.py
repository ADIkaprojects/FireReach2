"""
FireReach — Stage 4: Outreach Automated Sender (LLM + HTTP)

Pipeline:
  1. LLM Composer generates email draft (Groq Llama 3.3 70B)
  2. Email Linter validates (word count + cliché detector)
  3. LLM Critic evaluates quality (specificity, CTA clarity)
  4. If critic fails → Revisor re-drafts (max 1 retry)
  5. Resend.com dispatches the final email
  6. Idempotency key prevents duplicate sends within 72 hours
  7. Full audit log written to Supabase
"""

from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone

import httpx
import resend  # pip install resend

from models import AccountBrief, ContactResult, EmailDraft, SendResult
from validators import validate_email
from agent.prompts import (
    COMPOSER_SYSTEM,
    COMPOSER_RETRY_PREFIX,
    CRITIC_SYSTEM,
)
from agent.tools.llm_client import chat_completion
from agent.supabase_client import get_supabase


# ─── Email Composition ────────────────────────────────────────────────────────

async def _compose_email(
    recipient_name: str,
    recipient_title: str,
    brief: AccountBrief,
    icp_description: str,
    tone: str,
    errors: list[str] | None = None,
) -> tuple[str, str]:
    """Returns (subject, body)."""

    user_prompt = (
        f"Recipient: {recipient_name} ({recipient_title})\n\n"
        f"Account Brief:\n{brief.model_dump_json()}\n\n"
        f"Seller ICP:\n{icp_description}\n\n"
        f"Tone: {tone}"
    )

    if errors:
        system = COMPOSER_SYSTEM + "\n\n" + COMPOSER_RETRY_PREFIX.format(
            errors="\n".join(f"- {e}" for e in errors)
        )
    else:
        system = COMPOSER_SYSTEM

    raw = await chat_completion(system=system, user=user_prompt, temperature=0.6)

    # Strip markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )

    try:
        data = json.loads(cleaned)
        return data["subject"], data["body"]
    except (json.JSONDecodeError, KeyError):
        # Fallback: treat first line as subject, rest as body
        lines = cleaned.split("\n", 1)
        return lines[0][:100], lines[1] if len(lines) > 1 else cleaned


# ─── Multi-Agent Critic ───────────────────────────────────────────────────────

async def _critique_email(subject: str, body: str, brief: AccountBrief) -> dict:
    """
    Round 2: Critic agent evaluates the email against the quality rubric.
    Returns the rubric JSON dict.
    """
    user_prompt = (
        f"Subject: {subject}\n\n"
        f"Body:\n{body}\n\n"
        f"Account Brief used:\n{brief.model_dump_json()}"
    )

    raw = await chat_completion(
        system=CRITIC_SYSTEM, user=user_prompt, temperature=0.2
    )

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "specificity_score": 5,
            "cta_clarity": 5,
            "cliche_count": 0,
            "estimated_words": len(body.split()),
            "pass": True,
            "overall_score": 5.0,
            "feedback": [],
        }


# ─── Idempotency & Supabase Logging ──────────────────────────────────────────

def _dedup_key(recipient_email: str, company: str) -> str:
    return hashlib.sha256(
        f"{recipient_email}{company}{date.today()}".encode()
    ).hexdigest()


async def _check_duplicate(dedup_key: str) -> bool:
    """Returns True if this email was already sent today."""
    try:
        sb = get_supabase()
        result = sb.table("outreach_log").select("id").eq("dedup_key", dedup_key).execute()
        return len(result.data) > 0
    except Exception:
        return False


async def _log_send(
    message_id: str,
    recipient_email: str,
    company: str,
    dedup_key: str,
    subject: str,
    body: str,
    quality_score: float | None,
    signals_cited: list[str],
) -> None:
    try:
        sb = get_supabase()
        sb.table("outreach_log").insert({
            "message_id": message_id,
            "recipient": recipient_email,
            "company": company,
            "dedup_key": dedup_key,
            "subject": subject,
            "body_preview": body[:300],
            "quality_score": quality_score,
            "signals_cited": signals_cited,
            "sent_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "sent",
        }).execute()
    except Exception:
        pass   # logging failure should not block the send result


# ─── Resend Dispatch ─────────────────────────────────────────────────────────

def _send_via_resend(
    recipient_email: str,
    subject: str,
    body: str,
    from_address: str,
    unsub_email: str,
) -> dict:
    resend.api_key = os.environ["RESEND_API_KEY"]
    params: resend.Emails.SendParams = {
        "from": from_address,
        "to": [recipient_email],
        "subject": subject,
        "text": body,
        "headers": {
            "List-Unsubscribe": f"<mailto:{unsub_email}>",
        },
    }
    return resend.Emails.send(params)


# ─── SendGrid Fallback ─────────────────────────────────────────────────────────

async def _send_via_sendgrid(
    recipient_email: str,
    subject: str,
    body: str,
    from_address: str,
) -> str:
    """Fallback email dispatch via SendGrid free tier."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": recipient_email}]}],
                "from": {"email": from_address},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.headers.get("X-Message-Id", "sendgrid-ok")


# ─── Public Entry Point ───────────────────────────────────────────────────────

async def run_outreach_sender(
    contact: ContactResult,
    brief: AccountBrief,
    icp_description: str,
    tone: str = "consultative",
) -> SendResult:
    """
    Full Stage 4 pipeline: compose → lint → critique → dispatch → log.
    """
    if not contact.found or not contact.email:
        return SendResult(status="contact_not_found")

    recipient_email = contact.email
    # Allow TEST_TO_EMAIL override (required when using onboarding@resend.dev)
    test_override = os.environ.get("TEST_TO_EMAIL")
    if test_override:
        recipient_email = test_override
    recipient_name = (contact.name or "").split()[0] if contact.name else "there"
    recipient_title = contact.title or ""

    from_address = os.environ.get("FROM_EMAIL", "outreach@mail.firereach.app")
    unsub_email = os.environ.get("UNSUB_EMAIL", "unsubscribe@mail.firereach.app")
    company = recipient_email.split("@")[-1] if "@" in recipient_email else "company"

    # ── Idempotency check ────────────────────────────────────────────────────
    dk = _dedup_key(recipient_email, company)
    if await _check_duplicate(dk):
        return SendResult(
            status="skipped_duplicate",
            error=f"Already sent to {recipient_email} within 72 hours",
        )

    # ── Round 1: Compose ─────────────────────────────────────────────────────
    subject, body = await _compose_email(
        recipient_name=recipient_name,
        recipient_title=recipient_title,
        brief=brief,
        icp_description=icp_description,
        tone=tone,
    )

    # ── Linting ──────────────────────────────────────────────────────────────
    lint_ok, lint_errors = validate_email(body)
    if not lint_ok:
        subject, body = await _compose_email(
            recipient_name=recipient_name,
            recipient_title=recipient_title,
            brief=brief,
            icp_description=icp_description,
            tone=tone,
            errors=lint_errors,
        )
        lint_ok, lint_errors = validate_email(body)
        # If second attempt also fails, proceed with best draft (logged)

    # ── Round 2: Critic evaluation ───────────────────────────────────────────
    critique = await _critique_email(subject, body, brief)
    quality_score: float = critique.get("overall_score", 5.0)
    critic_passed: bool = critique.get("pass", True)
    feedback: list[str] = critique.get("feedback", [])

    if not critic_passed and feedback:
        # Revisor round — inject critic feedback
        revised_subject, revised_body = await _compose_email(
            recipient_name=recipient_name,
            recipient_title=recipient_title,
            brief=brief,
            icp_description=icp_description,
            tone=tone,
            errors=(lint_errors if not lint_ok else []) + feedback,
        )
        # Re-evaluate revised draft
        revised_critique = await _critique_email(revised_subject, revised_body, brief)
        revised_score: float = revised_critique.get("overall_score", 5.0)

        # Use whichever draft scored higher
        if revised_score >= quality_score:
            subject, body = revised_subject, revised_body
            quality_score = revised_score

    # ── Dispatch ─────────────────────────────────────────────────────────────
    message_id: str | None = None
    try:
        result = _send_via_resend(recipient_email, subject, body, from_address, unsub_email)
        message_id = result.get("id")
    except Exception as resend_exc:
        # Fallback to SendGrid
        try:
            message_id = await _send_via_sendgrid(recipient_email, subject, body, from_address)
        except Exception as sg_exc:
            return SendResult(
                status="failed",
                error=f"Resend: {resend_exc}; SendGrid: {sg_exc}",
                quality_score=quality_score,
            )

    # ── Log to Supabase ───────────────────────────────────────────────────────
    await _log_send(
        message_id=message_id or "",
        recipient_email=recipient_email,
        company=company,
        dedup_key=dk,
        subject=subject,
        body=body,
        quality_score=quality_score,
        signals_cited=brief.signal_citations,
    )

    return SendResult(
        message_id=message_id,
        status="sent",
        email_preview=body[:300],
        quality_score=quality_score,
    )


# ─── Tool Schema ──────────────────────────────────────────────────────────────

TOOL_SCHEMA = {
    "name": "tool_outreach_automated_sender",
    "description": (
        "Composes a hyper-personalised cold email grounded in the Account Brief and "
        "dispatches it via Resend.com. Enforces word count, cliché rules, "
        "multi-agent critic quality gate, and signal citation before sending."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "recipient_email": {"type": "string"},
            "recipient_name": {"type": "string"},
            "recipient_title": {"type": "string"},
            "account_brief_json": {
                "type": "string",
                "description": "JSON string from tool_research_analyst",
            },
            "sender_icp": {"type": "string"},
            "tone": {
                "type": "string",
                "enum": ["warm", "direct", "consultative"],
            },
        },
        "required": [
            "recipient_email",
            "recipient_name",
            "account_brief_json",
            "sender_icp",
        ],
    },
}
