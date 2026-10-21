"""Document builders and serializers for MongoDB collections."""
from datetime import datetime, timezone

from bson import ObjectId

PREVIEW_CHARS = 220


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_user_document(email: str, password_hash: str) -> dict:
    return {"email": email, "password": password_hash, "created_at": utcnow()}


def create_report_document(user_id, target_role: str, resume_text: str, results: dict) -> dict:
    return {
        "user_id": ObjectId(user_id),
        "target_role": target_role,
        "resume_text": resume_text,
        "results": results,
        "created_at": utcnow(),
    }


def _as_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if v not in (None, "")]


def normalize_results(raw) -> dict:
    """Return a predictable results dict from new or legacy stored reports."""
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    score = raw.get("match_score")
    return {
        "match_score": score if isinstance(score, int) else None,
        "summary": str(raw.get("summary") or ""),
        "skills": _as_list(raw.get("skills")),
        "missing_skills": _as_list(raw.get("missing_skills")),
        # Legacy reports may have used a capitalised "Roadmap" key.
        "roadmap": _as_list(raw.get("roadmap") or raw.get("Roadmap")),
        "interview_questions": _as_list(raw.get("interview_questions")),
    }


def format_report(doc: dict) -> dict:
    """Convert a stored report to a template-friendly dict (no ObjectIds)."""
    created = doc.get("created_at")
    if created is None and isinstance(doc.get("_id"), ObjectId):
        created = doc["_id"].generation_time
    resume = str(doc.get("resume_text") or "")
    preview = resume[:PREVIEW_CHARS] + ("…" if len(resume) > PREVIEW_CHARS else "")
    return {
        "id": str(doc.get("_id", "")),
        "target_role": str(doc.get("target_role") or doc.get("user_goal") or ""),
        "resume_preview": preview,
        "created": created.strftime("%d %b %Y, %H:%M UTC") if created else "",
        "analysis": normalize_results(doc.get("results")),
    }
