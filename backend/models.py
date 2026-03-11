"""
FireReach — Pydantic Schemas for all tools and agent state.
All tool I/O is validated at stage boundaries — never silently corrupted.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ─── Stage 1: Signal Harvester ─────────────────────────────────────────────

class FundingResult(BaseModel):
    round: Optional[str] = None
    amount: Optional[str] = None
    date: Optional[str] = None
    source_url: Optional[str] = None
    fetched_at: Optional[str] = None
    reason: Optional[str] = None   # populated when value is null


class HiringRole(BaseModel):
    title: str
    ats: Literal["greenhouse", "lever", "tavily"]
    posted: Optional[str] = None


class NewsResult(BaseModel):
    headline: Optional[str] = None
    source: Optional[str] = None
    date: Optional[str] = None
    reason: Optional[str] = None


class SignalResult(BaseModel):
    funding: Optional[FundingResult] = None
    hiring_roles: list[HiringRole] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    news: Optional[NewsResult] = None

    def non_null_keys(self) -> list[str]:
        keys = []
        if self.funding and self.funding.round:
            keys.append("funding")
        if self.hiring_roles:
            keys.append("hiring_roles")
        if self.tech_stack:
            keys.append("tech_stack")
        if self.news and self.news.headline:
            keys.append("news")
        return keys


# ─── Stage 2: Contact Resolver ──────────────────────────────────────────────

class ContactResult(BaseModel):
    found: bool
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    confidence: float = 0.0
    source: Optional[str] = None
    smtp_verified: bool = False
    reason: Optional[str] = None   # populated when found=False


# ─── Stage 3: Research Analyst ──────────────────────────────────────────────

class AccountBrief(BaseModel):
    p1: str
    p2: str
    pain_points: list[str] = Field(default_factory=list)
    signal_citations: list[str] = Field(default_factory=list)


# ─── Stage 4: Outreach Sender ───────────────────────────────────────────────

class EmailDraft(BaseModel):
    subject: str
    body: str
    word_count: int
    quality_score: Optional[float] = None
    critic_feedback: list[str] = Field(default_factory=list)
    linting_passed: bool = False


class SendResult(BaseModel):
    message_id: Optional[str] = None
    status: Literal["sent", "failed", "skipped_duplicate", "contact_not_found"]
    email_preview: Optional[str] = None
    quality_score: Optional[float] = None
    error: Optional[str] = None


# ─── Agent State ────────────────────────────────────────────────────────────

class AgentState(BaseModel):
    job_id: str
    company_name: str
    company_domain: str
    icp_description: str
    tone: Literal["warm", "direct", "consultative"] = "consultative"

    messages: list[dict] = Field(default_factory=list)
    signals: Optional[SignalResult] = None
    contact: Optional[ContactResult] = None
    brief: Optional[AccountBrief] = None
    email_result: Optional[SendResult] = None

    iteration: int = 0
    status: Literal["queued", "running", "done", "error"] = "queued"
    error_message: Optional[str] = None
    icp_score: Optional[int] = None
    icp_label: Optional[str] = None


# ─── API Request / Response ─────────────────────────────────────────────────

class OutreachRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    company_domain: str = Field(..., min_length=3, max_length=200)
    icp_description: str = Field(..., min_length=10, max_length=2000)
    tone: Literal["warm", "direct", "consultative"] = "consultative"


class JobCreatedResponse(BaseModel):
    job_id: str


class AgentEvent(BaseModel):
    job_id: str
    stage: Optional[str] = None
    message: Optional[str] = None
    data: Optional[dict] = None
    status: Literal["queued", "running", "done", "error"]
    timestamp: str
