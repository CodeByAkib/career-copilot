import io

import pytest
from bson import ObjectId

from tests.conftest import (RESUME, get_token, make_docx, make_pdf, post, signup_and_login)


# ---------------------------------------------------------------- auth/session
def test_pages_render(client):
    for path in ("/login", "/signup"):
        r = client.get(path)
        assert r.status_code == 200 and "csrf_token" in r.get_data(as_text=True)
    assert client.get("/").status_code == 302
    assert client.get("/nope").status_code == 404


def test_protected_routes_redirect(client):
    for path in ("/dashboard", "/history"):
        r = client.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert client.post("/dashboard", data={}).status_code == 400  # no CSRF token


def test_signup_validation(client):
    r = post(client, "/signup", {"email": "bad", "password": "password123"}, token_from="/signup")
    assert r.status_code == 400 and "valid email" in r.get_data(as_text=True)
    r = post(client, "/signup", {"email": "a@b.co", "password": "short"}, token_from="/signup")
    assert r.status_code == 400 and "at least 8" in r.get_data(as_text=True)


def test_signup_stores_hash_and_blocks_duplicates(client, database):
    r = post(client, "/signup", {"email": "A@Example.com ", "password": "password123"}, token_from="/signup")
    assert r.status_code == 302
    user = database.users.find_one({"email": "a@example.com"})
    assert user and user["password"] != "password123" and user["password"].count("$") >= 2
    r = post(client, "/signup", {"email": "a@example.com", "password": "password123"}, token_from="/signup")
    assert r.status_code == 409 and database.users.count_documents({}) == 1


def test_login_success_failure_and_logout(client):
    post(client, "/signup", {"email": "a@example.com", "password": "password123"}, token_from="/signup")
    assert post(client, "/login", {"email": "a@example.com", "password": "wrongpass1"}).status_code == 401
    assert post(client, "/login", {"email": "nobody@example.com", "password": "password123"}).status_code == 401
    r = post(client, "/login", {"email": "a@example.com", "password": "password123"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    assert client.get("/dashboard").status_code == 200
    assert client.get("/logout").status_code == 405           # logout is POST-only
    assert post(client, "/logout", token_from="/dashboard").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_deleted_user_session_is_dropped(client, database):
    signup_and_login(client)
    database.users.delete_many({})
    assert client.get("/dashboard").status_code == 302


def test_security_headers_and_cookie_flags(client):
    r = client.get("/login")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]
    r = signup_and_login(client)
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


# ------------------------------------------------------------------- dashboard
def analyse(client, role="Python Developer", resume=RESUME, files=None):
    data = {"role": role, "resume": resume}
    if files:
        data.update(files)
    return post(client, "/dashboard", data, token_from="/dashboard", content_type="multipart/form-data")


def test_text_analysis_saved_once(client, database, analyzer):
    signup_and_login(client)
    r = analyse(client)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Python" in html and "Learn Docker basics" in html and "72%" in html
    assert len(analyzer.calls) == 1 and database.reports.count_documents({}) == 1
    assert "history" not in database.list_collection_names()   # no duplicate history copy
    doc = database.reports.find_one()
    assert isinstance(doc["user_id"], ObjectId) and doc["target_role"] == "Python Developer"


@pytest.mark.parametrize("role,resume,msg", [
    ("", RESUME, "target job role"),
    ("Dev", "", "paste your resume"),
    ("Dev", "tiny", "too short"),
    ("x", RESUME, "too short"),
])
def test_validation_blocks_ai_call(client, analyzer, database, role, resume, msg):
    signup_and_login(client)
    r = analyse(client, role=role, resume=resume)
    assert r.status_code == 400 and msg in r.get_data(as_text=True)
    assert analyzer.calls == [] and database.reports.count_documents({}) == 0


def test_file_uploads(client, analyzer):
    signup_and_login(client)
    pdf = make_pdf("Senior Python engineer with Flask, MongoDB and Docker experience.\n" * 2)
    r = analyse(client, resume="", files={"file": (io.BytesIO(pdf), "cv.pdf")})
    assert r.status_code == 200 and "Flask" in analyzer.calls[-1][0]
    docx_bytes = make_docx("Backend engineer with extensive Python, Flask and SQL experience in production.")
    r = analyse(client, resume="", files={"file": (io.BytesIO(docx_bytes), "cv.docx")})
    assert r.status_code == 200 and len(analyzer.calls) == 2


def test_bad_uploads_are_reported(client, analyzer):
    signup_and_login(client)
    for name, content, msg in [("cv.txt", b"hello", "Unsupported"),
                               ("cv.pdf", b"not a pdf", "not a real PDF"),
                               ("cv.docx", b"%PDF-1.4", "not a real DOCX")]:
        r = analyse(client, files={"file": (io.BytesIO(content), name)})
        assert r.status_code == 400 and msg in r.get_data(as_text=True)
    assert analyzer.calls == []


def test_oversized_upload_rejected(client, analyzer):
    signup_and_login(client)
    big = io.BytesIO(b"%PDF-" + b"0" * (2 * 1024 * 1024))
    r = analyse(client, files={"file": (big, "cv.pdf")})
    assert r.status_code == 413 and "too large" in r.get_data(as_text=True) and analyzer.calls == []


def test_ai_error_not_saved(client, app, database):
    signup_and_login(client)
    app.extensions["analyzer"] = lambda t, r: {"error": "Gemini is down"}
    r = analyse(client)
    assert r.status_code == 502 and "Gemini is down" in r.get_data(as_text=True)
    assert database.reports.count_documents({}) == 0


def test_user_input_is_escaped(client, app):
    signup_and_login(client)
    app.extensions["analyzer"] = lambda t, r: {"skills": ["<script>alert(1)</script>"], "match_score": 5}
    html = analyse(client).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


# --------------------------------------------------------------------- history
def test_history_empty_state(client):
    signup_and_login(client)
    assert "No analyses yet" in client.get("/history").get_data(as_text=True)


def test_history_is_per_user_and_ordered(client, app, database, analyzer):
    signup_and_login(client, "a@example.com")
    analyse(client, role="Role One")
    analyse(client, role="Role Two")
    post(client, "/logout", token_from="/dashboard")
    signup_and_login(client, "b@example.com")
    analyse(client, role="Bob Role")
    html = client.get("/history").get_data(as_text=True)
    assert "Bob Role" in html and "Role One" not in html
    post(client, "/logout", token_from="/dashboard")
    post(client, "/login", {"email": "a@example.com", "password": "password123"})
    html = client.get("/history").get_data(as_text=True)
    assert html.index("Role Two") < html.index("Role One") and "Bob Role" not in html


def test_history_renders_legacy_documents(client, database):
    signup_and_login(client)
    uid = database.users.find_one()["_id"]
    database.reports.insert_one({"user_id": uid, "user_goal": "Legacy Role", "resume_text": "old resume",
                                 "results": {"skills": ["COBOL"], "Roadmap": ["Old step"]}})
    html = client.get("/history").get_data(as_text=True)
    assert "Legacy Role" in html and "COBOL" in html and "Old step" in html


def test_unique_email_index_created(app, database):
    app.extensions["get_db"]()
    names = {i["name"] for i in database.users.list_indexes()}
    assert "uniq_email" in names


def test_database_outage_shows_503(settings, analyzer):
    from pymongo.errors import ServerSelectionTimeoutError
    from app import create_app

    class BrokenDB:
        def __getitem__(self, name):
            raise ServerSelectionTimeoutError("No replica set members match selector Primary()")

    c = create_app(settings, database=BrokenDB(), analyzer=analyzer).test_client()
    r = post(c, "/login", {"email": "a@example.com", "password": "password123"})
    assert r.status_code == 503 and "Database unavailable" in r.get_data(as_text=True)
    assert "Primary()" not in r.get_data(as_text=True)   # internals are not shown to users
