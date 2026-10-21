"""Input validation helpers. Each returns (clean_value, error_message_or_None)."""
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128
MIN_RESUME_CHARS = 50
MAX_RESUME_CHARS = 30000
MIN_ROLE, MAX_ROLE = 2, 100
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Remove NUL/control characters that break storage or prompts."""
    return _CONTROL_RE.sub("", text or "").strip()


def validate_email(raw):
    email = (raw or "").strip().lower()
    if not email:
        return "", "Email is required."
    if len(email) > 254 or not EMAIL_RE.match(email):
        return email, "Please enter a valid email address."
    return email, None


def validate_password(password):
    if not password:
        return "Password is required."
    if len(password) < MIN_PASSWORD:
        return f"Password must contain at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Password must be at most {MAX_PASSWORD} characters."
    return None


def validate_role(raw):
    role = " ".join(clean_text(raw).split())
    if not role:
        return "", "Please enter your target job role."
    if len(role) < MIN_ROLE:
        return role, "Target job role is too short."
    if len(role) > MAX_ROLE:
        return role, f"Target job role must be at most {MAX_ROLE} characters."
    return role, None


def validate_resume_text(raw):
    text = clean_text(raw)
    if not text:
        return "", "Please paste your resume or upload a PDF/DOCX file."
    if len(text) < MIN_RESUME_CHARS:
        return text, f"The resume text is too short (minimum {MIN_RESUME_CHARS} characters)."
    if len(text) > MAX_RESUME_CHARS:
        return text, f"The resume text is too long (maximum {MAX_RESUME_CHARS:,} characters)."
    return text, None
