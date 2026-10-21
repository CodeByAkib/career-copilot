"""Career Copilot - Flask application."""
import hmac
import logging
import os
import secrets
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import db as dbmod
from ai import make_analyzer
from config import ConfigError, Settings, load_settings
from models import create_report_document, create_user_document, format_report, normalize_results
from resume_parser import ResumeInputError, extract_resume_text
from validation import (validate_email, validate_password, validate_resume_text,
                        validate_role)

logger = logging.getLogger("career_copilot")
HISTORY_LIMIT = 50
_DUMMY_HASH = generate_password_hash("not-a-real-password")  # equalises login timing


def create_app(settings: Settings = None, database=None, analyzer=None) -> Flask:
    """Application factory. `database` and `analyzer` can be injected (used by tests)."""
    settings = settings or load_settings()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        MAX_CONTENT_LENGTH=settings.max_upload_mb * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
        PERMANENT_SESSION_LIFETIME=7 * 24 * 3600,
    )
    app.extensions["settings"] = settings
    app.extensions["analyzer"] = analyzer or make_analyzer(settings)
    state = {"client": None, "db": database, "indexes": False}
    app.extensions["db_state"] = state

    def get_db():
        if state["db"] is None:
            state["client"] = dbmod.create_client(settings)
            state["db"] = state["client"][settings.mongodb_database]
        if not state["indexes"]:
            dbmod.ensure_indexes(state["db"])
            state["indexes"] = True
        return state["db"]

    app.extensions["get_db"] = get_db

    # ---------------------------------------------------------------- security
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_from_csrf():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
            expected = session.get("_csrf") or ""
            if not expected or not hmac.compare_digest(sent, expected):
                abort(400, "Your session expired or the form was invalid. Please reload the page and try again.")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'",
        )
        if request.endpoint in {"login", "signup", "dashboard", "history"}:
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return redirect(url_for("login"))
            try:
                user = get_db()[dbmod.USERS].find_one({"_id": ObjectId(user_id)})
            except InvalidId:
                user = None
            if not user:
                session.clear()
                return redirect(url_for("login"))
            g.user = user
            return view(*args, **kwargs)
        return wrapped

    @app.context_processor
    def inject_user():
        return {"logged_in": bool(session.get("user_id")), "current_email": session.get("email")}

    # ------------------------------------------------------------------ routes
    @app.route("/")
    def home():
        return redirect(url_for("dashboard" if session.get("user_id") else "login"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            email, error = validate_email(request.form.get("email"))
            password = request.form.get("password", "")
            error = error or validate_password(password)
            if error:
                return render_template("signup.html", error=error, email=email), 400
            try:
                get_db()[dbmod.USERS].insert_one(
                    create_user_document(email, generate_password_hash(password)))
            except DuplicateKeyError:
                return render_template("signup.html", error="An account with this email already exists.", email=email), 409
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email, _ = validate_email(request.form.get("email"))
            password = request.form.get("password", "")
            user = get_db()[dbmod.USERS].find_one({"email": email}) if email else None
            valid = check_password_hash(user["password"] if user else _DUMMY_HASH, password)
            if user and valid:
                session.clear()
                session.permanent = True
                session["user_id"] = str(user["_id"])
                session["email"] = user["email"]
                return redirect(url_for("dashboard"))
            return render_template("login.html", error="Invalid email or password.", email=email), 401
        return render_template("login.html")

    def _dashboard(status=200, **ctx):
        form = ctx.pop("form", {})
        return render_template("dashboard.html", form=form, **ctx), status

    @app.route("/dashboard", methods=["GET", "POST"])
    @login_required
    def dashboard():
        if request.method == "GET":
            return _dashboard()

        form = {"role": request.form.get("role", ""), "resume": request.form.get("resume", "")}
        role, error = validate_role(form["role"])
        if error:
            return _dashboard(400, error=error, form=form)

        uploaded = request.files.get("file")
        try:
            if uploaded and uploaded.filename:
                raw_text = extract_resume_text(uploaded.filename, uploaded.read())
            else:
                raw_text = form["resume"]
        except ResumeInputError as exc:
            return _dashboard(400, error=str(exc), form=form)

        resume_text, error = validate_resume_text(raw_text)
        if error:
            return _dashboard(400, error=error, form=form)

        result = app.extensions["analyzer"](resume_text, role)
        if not isinstance(result, dict) or result.get("error"):
            message = result.get("error") if isinstance(result, dict) else "Invalid response from the analyzer."
            return _dashboard(502, error=message, form=form)

        warning = None
        try:
            get_db()[dbmod.REPORTS].insert_one(
                create_report_document(g.user["_id"], role, resume_text, result))
        except PyMongoError as exc:
            logger.error("Could not save report: %s", dbmod.describe_error(exc))
            warning = "Your analysis is shown below but could not be saved to your history."
        return _dashboard(analysis=normalize_results(result), warning=warning,
                          target_role=role, model=result.get("model"), form=form)

    @app.route("/history")
    @login_required
    def history():
        docs = (get_db()[dbmod.REPORTS].find({"user_id": g.user["_id"]})
                .sort("_id", -1).limit(HISTORY_LIMIT))
        return render_template("history.html", reports=[format_report(d) for d in docs])

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    # ---------------------------------------------------------- error handling
    @app.errorhandler(PyMongoError)
    def database_error(exc):
        logger.error("Database error: %s", dbmod.describe_error(exc))
        return render_template(
            "error.html", code=503, title="Database unavailable",
            message="The database could not be reached. Please try again in a moment."), 503

    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages = {
            404: "That page does not exist.",
            405: "That action is not allowed here.",
            413: f"The uploaded file is too large (limit {settings.max_upload_mb} MB).",
        }
        message = messages.get(exc.code) or exc.description
        return render_template("error.html", code=exc.code, title=exc.name, message=message), exc.code

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        logger.exception("Unhandled error")
        return render_template("error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500

    # Try to create indexes at startup, but never block the app if Atlas is unreachable.
    if database is None:
        try:
            get_db()
        except PyMongoError as exc:
            logger.warning("MongoDB not reachable at startup: %s", dbmod.describe_error(exc))
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        cfg = load_settings()
    except ConfigError as err:
        raise SystemExit(str(err))
    create_app(cfg).run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=cfg.debug)
