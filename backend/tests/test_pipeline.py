"""
FireReach — Eval Suite
======================
Tests the full pipeline against 5 real companies and records metrics.

Run:
    cd backend
    python -m pytest tests/test_pipeline.py -v --tb=short

Or as a standalone script (no pytest):
    python tests/test_pipeline.py

Results are written to: backend/tests/eval_results.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Allow importing from the backend package when run directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.loop import run_agent
from models import AgentState, ICPProfile, OutreachRequest

# ─── Eval companies ──────────────────────────────────────────────────────────

EVAL_CASES = [
    {
        "company_name": "Retool",
        "company_domain": "retool.com",
        "icp": ICPProfile(
            industry="SaaS",
            size_range="200-1000",
            funding_stage="Series C+",
            geography=["US"],
            pain_points="Internal tooling is slow, engineers spend weeks building admin panels",
            your_product="Low-code internal tool builder for developer teams",
            target_titles=["CTO", "VP Engineering"],
        ),
        "tone": "direct",
    },
    {
        "company_name": "Linear",
        "company_domain": "linear.app",
        "icp": ICPProfile(
            industry="SaaS",
            size_range="50-200",
            funding_stage="Series B",
            geography=["US", "Europe"],
            pain_points="Engineering teams waste time in bloated issue trackers",
            your_product="Modern project management for software teams",
            target_titles=["CTO", "VP Engineering", "DevOps Lead"],
        ),
        "tone": "consultative",
    },
    {
        "company_name": "Vercel",
        "company_domain": "vercel.com",
        "icp": ICPProfile(
            industry="SaaS",
            size_range="200-1000",
            funding_stage="Series C+",
            geography=["US", "Global"],
            pain_points="Frontend deployments are slow and hard to preview across environments",
            your_product="Edge deployment platform for frontend developers",
            target_titles=["CTO", "VP Engineering"],
        ),
        "tone": "direct",
    },
    {
        "company_name": "Stripe",
        "company_domain": "stripe.com",
        "icp": ICPProfile(
            industry="Fintech",
            size_range="1000+",
            funding_stage="IPO",
            geography=["US", "Global"],
            pain_points="Payment fraud, compliance complexity, developer onboarding friction",
            your_product="Payment infrastructure and fraud prevention for internet companies",
            target_titles=["CTO", "CFO", "VP Engineering"],
        ),
        "tone": "consultative",
    },
    {
        "company_name": "Notion",
        "company_domain": "notion.com",
        "icp": ICPProfile(
            industry="SaaS",
            size_range="200-500",
            funding_stage="Series C+",
            geography=["US", "Europe", "Asia"],
            pain_points="Knowledge management is scattered across Confluence, Docs, spreadsheets",
            your_product="All-in-one workspace for notes, wikis, and project tracking",
            target_titles=["CTO", "VP Product", "CEO"],
        ),
        "tone": "warm",
    },
]

# ─── Single case runner ───────────────────────────────────────────────────────

async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Runs one company through the full pipeline and returns metrics."""
    request = OutreachRequest(
        company_name=case["company_name"],
        company_domain=case["company_domain"],
        icp=case["icp"],
        tone=case["tone"],
    )

    state = AgentState(
        job_id=f"eval_{case['company_domain'].replace('.', '_')}",
        company_name=request.company_name,
        company_domain=request.company_domain,
        icp=request.icp,
        icp_description=(
            f"Industry: {request.icp.industry}\n"
            f"Size: {request.icp.size_range}\n"
            f"Funding: {request.icp.funding_stage}\n"
            f"Geography: {', '.join(request.icp.geography)}\n"
            f"Pain points: {request.icp.pain_points}\n"
            f"Product: {request.icp.your_product}\n"
            f"Target titles: {', '.join(request.icp.target_titles)}"
        ),
        tone=request.tone,  # type: ignore[arg-type]
    )

    t0 = time.perf_counter()
    try:
        final_state = await run_agent(state)
    except Exception as exc:
        return {
            "company": case["company_name"],
            "error": str(exc),
            "duration_s": round(time.perf_counter() - t0, 2),
            "passed": False,
        }
    duration = round(time.perf_counter() - t0, 2)

    # ── Metric extraction ──
    signals_found = 0
    if final_state.signals:
        sig = final_state.signals
        if sig.funding_signal:  signals_found += 1
        if sig.hiring_signal:   signals_found += 1
        if sig.tech_stack:      signals_found += 1
        if getattr(sig, "security_signal", None): signals_found += 1
        if getattr(sig, "sales_signal",    None): signals_found += 1
        if getattr(sig, "market_signal",   None): signals_found += 1

    contact_resolved = bool(
        final_state.contact and final_state.contact.email
    )
    icp_score = final_state.icp_score or 0
    icp_tier  = final_state.icp_label or "unknown"
    email_sent = final_state.status == "sent"
    skipped    = final_state.status in ("skipped_poor_fit", "queued_potential")
    quality    = None
    if final_state.send_result:
        quality = getattr(final_state.send_result, "quality_score", None)

    result: dict[str, Any] = {
        "company":          case["company_name"],
        "domain":           case["company_domain"],
        "status":           final_state.status,
        "signals_found":    signals_found,
        "contact_resolved": contact_resolved,
        "contact_email":    final_state.contact.email if final_state.contact else None,
        "icp_score":        icp_score,
        "icp_tier":         icp_tier,
        "email_sent":       email_sent,
        "skipped":          skipped,
        "quality_score":    quality,
        "duration_s":       duration,
        "passed":           contact_resolved and icp_score > 0,
    }

    # ── Assertions (soft — log failures, don't raise) ──
    failures: list[str] = []
    if not contact_resolved:
        failures.append("contact NOT resolved")
    if not (0 <= icp_score <= 100):
        failures.append(f"ICP score out of range: {icp_score}")
    if final_state.status not in (
        "sent", "skipped_poor_fit", "queued_potential", "error", "failed"
    ):
        failures.append(f"unexpected status: {final_state.status}")

    result["assertion_failures"] = failures
    return result


# ─── Main harness ─────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n🔥 FireReach Eval Suite — running 5 companies\n" + "─" * 55)

    results: list[dict[str, Any]] = []
    for i, case in enumerate(EVAL_CASES, 1):
        print(f"[{i}/5] {case['company_name']} ({case['company_domain']}) …", flush=True)
        result = await run_case(case)
        results.append(result)

        status_icon = "✅" if result.get("passed") else "❌"
        print(
            f"      {status_icon}  status={result.get('status')}  "
            f"contact={'✓' if result.get('contact_resolved') else '✗'}  "
            f"icp_score={result.get('icp_score', 'N/A')}  "
            f"tier={result.get('icp_tier', '?')}  "
            f"({result.get('duration_s', '?')}s)"
        )
        if result.get("assertion_failures"):
            for f in result["assertion_failures"]:
                print(f"      ⚠ {f}")

    # ── Summary ──
    total     = len(results)
    passed    = sum(1 for r in results if r.get("passed"))
    resolved  = sum(1 for r in results if r.get("contact_resolved"))
    sent      = sum(1 for r in results if r.get("email_sent"))
    skipped   = sum(1 for r in results if r.get("skipped"))
    avg_score = sum(r.get("icp_score", 0) for r in results) / total

    print("\n" + "─" * 55)
    print(f"  Passed:            {passed}/{total}")
    print(f"  Contact resolved:  {resolved}/{total}  ({100*resolved//total}%)")
    print(f"  Emails sent:       {sent}/{total}")
    print(f"  Skipped (low ICP): {skipped}/{total}")
    print(f"  Avg ICP score:     {avg_score:.1f}/100")
    print("─" * 55)

    # Write JSON results
    out_path = Path(__file__).parent / "eval_results.json"
    out_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total": total, "passed": passed,
                    "contact_resolution_rate": f"{100*resolved//total}%",
                    "emails_sent": sent, "skipped": skipped,
                    "avg_icp_score": round(avg_score, 1),
                },
                "results": results,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\n📄 Results saved to {out_path}\n")


# ─── pytest compatibility ─────────────────────────────────────────────────────

def test_retool():
    result = asyncio.run(run_case(EVAL_CASES[0]))
    assert result["icp_score"] >= 0, "ICP score should be non-negative"
    assert result["icp_score"] <= 100, "ICP score should be ≤ 100"


def test_linear():
    result = asyncio.run(run_case(EVAL_CASES[1]))
    assert result["icp_score"] >= 0
    assert result["icp_score"] <= 100


def test_vercel():
    result = asyncio.run(run_case(EVAL_CASES[2]))
    assert result["icp_score"] >= 0
    assert result["icp_score"] <= 100


def test_stripe():
    result = asyncio.run(run_case(EVAL_CASES[3]))
    assert result["icp_score"] >= 0
    assert result["icp_score"] <= 100


def test_notion():
    result = asyncio.run(run_case(EVAL_CASES[4]))
    assert result["icp_score"] >= 0
    assert result["icp_score"] <= 100


if __name__ == "__main__":
    asyncio.run(main())
