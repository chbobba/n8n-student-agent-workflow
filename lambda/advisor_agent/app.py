"""
AI Student Grade Improvement Advisor - Advisor Agent API (AWS Lambda)

Purpose:
- Provide risk score + explainable factors + study recommendations
- Designed to be called from n8n via HTTP (API Gateway / Lambda Function URL)

Status:
- Pilot / Ongoing development

PII Safety:
- Do not log student names/emails. Send an opaque student_token from n8n if needed.
"""

from __future__ import annotations
import json
import os
import time
import logging
from typing import Any, Dict, List, Tuple

log = logging.getLogger()
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))

RISK_THRESHOLD = float(os.getenv("RISK_THRESHOLD", "0.75"))


def _safe_json(body: str) -> Dict[str, Any]:
    try:
        return json.loads(body or "{}")
    except Exception:
        return {}


def _days_inactive_to_score(days_inactive: float) -> Tuple[float, str | None]:
    if days_inactive >= 7:
        return 0.30, "Inactive 7+ days"
    if days_inactive >= 4:
        return 0.18, "Inactive 4+ days"
    if days_inactive >= 2:
        return 0.08, "Inactive 2+ days"
    return 0.0, None


def _missing_to_score(missing_14d: int) -> Tuple[float, str | None]:
    if missing_14d >= 3:
        return 0.35, "3+ missing assignments (14d)"
    if missing_14d == 2:
        return 0.25, "2 missing assignments (14d)"
    if missing_14d == 1:
        return 0.15, "1 missing assignment (14d)"
    return 0.0, None


def _grade_to_score(avg_grade_pct: int) -> Tuple[float, str | None]:
    if avg_grade_pct < 70:
        return 0.35, "Average grade < 70%"
    if avg_grade_pct < 80:
        return 0.20, "Average grade < 80%"
    if avg_grade_pct < 85:
        return 0.10, "Average grade < 85%"
    return 0.0, None


def compute_risk(payload: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Explainable scoring model (good for pilots).
    Replace with ML later if needed.
    """
    missing_14d = int(payload.get("missing_14d", 0))
    avg_grade_pct = int(payload.get("avg_grade_pct", 0))
    days_inactive = float(payload.get("days_inactive", 0))

    score = 0.0
    factors: List[str] = []

    s, f = _missing_to_score(missing_14d)
    score += s
    if f: factors.append(f)

    s, f = _grade_to_score(avg_grade_pct)
    score += s
    if f: factors.append(f)

    s, f = _days_inactive_to_score(days_inactive)
    score += s
    if f: factors.append(f)

    return min(score, 1.0), factors


def build_recommendations(payload: Dict[str, Any], risk_score: float, factors: List[str]) -> List[str]:
    """
    Deterministic recommendations (no external API required).
    n8n can email these directly to students/advisors.
    """
    recs: List[str] = []

    missing_14d = int(payload.get("missing_14d", 0))
    avg_grade_pct = int(payload.get("avg_grade_pct", 0))
    days_inactive = float(payload.get("days_inactive", 0))
    submitted_14d = int(payload.get("submitted_14d", 0))

    # Priority actions
    if missing_14d > 0:
        recs.append("Make a 48-hour plan to complete the missing assignments (start with the highest-weight items).")
        recs.append("Email the instructor to confirm deadlines and ask what to prioritize first.")

    if avg_grade_pct < 80:
        recs.append("Block 45–60 minutes daily for targeted practice on weak topics (quiz + review mistakes).")
        recs.append("Attend office hours or tutoring this week with 3 specific questions prepared.")

    if days_inactive >= 4:
        recs.append("Log in today and complete one small task (discussion post, quiz attempt, or reading notes) to restart momentum.")

    # Study plan suggestions
    if risk_score >= RISK_THRESHOLD:
        recs.append("Create a weekly schedule: 3 study sessions + 1 catch-up session, and track completion.")
        recs.append("Use active recall: summarize each module in 5 bullets, then self-test without notes.")
    else:
        recs.append("Keep current pace—set one weekly checkpoint to ensure no assignments are missed.")

    # Engagement guidance
    if submitted_14d == 0:
        recs.append("Start with the easiest assignment to build confidence, then move to the next due item.")

    # Explainability
    if factors:
        recs.append(f"Why this plan: {', '.join(factors)}.")

    return recs


def response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """API Gateway/Lambda URL friendly response with basic CORS."""
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Expected POST JSON from n8n (example):
    {
      "student_token":"abc123",
      "term":"2026SP",
      "course_id":"CSD-310",
      "avg_grade_pct":72,
      "missing_14d":2,
      "submitted_14d":3,
      "days_inactive":5
    }
    """
    # Preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return response(200, {"ok": True})

    payload = _safe_json(event.get("body", ""))

    # Don’t log full payload (PII risk). Log safe metadata only.
    log.info("AdvisorAgent invoked. keys=%s", sorted(list(payload.keys())))

    risk, factors = compute_risk(payload)
    recs = build_recommendations(payload, risk, factors)

    out = {
        "ok": True,
        "risk_score": round(risk, 3),
        "risk_level": "HIGH" if risk >= RISK_THRESHOLD else "LOW",
        "factors": factors,
        "recommendations": recs,
        "generated_at_epoch": int(time.time()),
    }
    return response(200, out)
