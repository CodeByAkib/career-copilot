from bson import ObjectId
from werkzeug.security import check_password_hash, generate_password_hash

from models import create_report_document, create_user_document, format_report, normalize_results
from validation import validate_email, validate_password, validate_resume_text, validate_role


def test_password_hash_roundtrip():
    h = generate_password_hash("password123")
    assert h != "password123" and check_password_hash(h, "password123") and not check_password_hash(h, "nope")
    assert "password" not in create_user_document("a@b.co", h)["password"][:8]


def test_email_and_password_rules():
    assert validate_email("  A@B.CO ")[0] == "a@b.co" and validate_email("A@B.CO")[1] is None
    assert validate_email("bad")[1] and validate_email("")[1]
    assert validate_password("short") and validate_password("longenough1") is None


def test_role_and_resume_rules():
    assert validate_role("  Python   Developer ")[0] == "Python Developer"
    assert validate_role("")[1] and validate_role("x" * 101)[1]
    assert validate_resume_text("too short")[1]
    assert validate_resume_text("x" * 40000)[1]
    assert validate_resume_text("a\x00b " * 30)[1] is None and "\x00" not in validate_resume_text("a\x00b " * 30)[0]


def test_normalize_results_legacy_and_string():
    legacy = {"skills": ["a"], "Roadmap": ["step"], "missing_skills": None}
    n = normalize_results(legacy)
    assert n["roadmap"] == ["step"] and n["missing_skills"] == [] and n["match_score"] is None
    assert normalize_results('{"skills": ["x"]}')["skills"] == ["x"]
    assert normalize_results("not json")["skills"] == []


def test_report_document_and_formatting():
    uid = ObjectId()
    doc = create_report_document(str(uid), "Dev", "r" * 300, {"skills": ["a"]})
    assert doc["user_id"] == uid
    doc["_id"] = ObjectId()
    f = format_report(doc)
    assert f["target_role"] == "Dev" and f["resume_preview"].endswith("…") and f["created"]
    assert isinstance(f["id"], str)
    legacy = format_report({"_id": ObjectId(), "user_goal": "Old", "resume_text": "x", "results": {}})
    assert legacy["target_role"] == "Old" and legacy["created"]
