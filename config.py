"""Environment-based configuration with clear, secret-safe error messages."""
import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


_PLACEHOLDER_SECRETS = {"change-me", "changeme", "your-secret-key", "replace-me"}
_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,63}$")


@dataclass(frozen=True)
class Settings:
    secret_key: str
    mongodb_uri: str
    mongodb_database: str = "career_copilot"
    mongodb_timeout_ms: int = 10000
    mongodb_tls_ca_file: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_models: Tuple[str, ...] = ("gemini-3.5-flash-lite", "gemini-2.5-flash")
    max_upload_mb: int = 5
    session_cookie_secure: bool = False
    debug: bool = False


def _as_bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_int(env: Mapping[str, str], name: str, default: int, errors: list) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError
        return value
    except ValueError:
        errors.append(f"{name} must be a positive integer.")
        return default


def load_settings(env: Optional[Mapping[str, str]] = None, load_env_file: bool = True) -> Settings:
    """Load and validate settings. Raises ConfigError listing every problem found."""
    if env is None:
        if load_env_file:
            load_dotenv()
        env = os.environ

    errors = []

    secret_key = (env.get("FLASK_SECRET_KEY") or "").strip()
    if not secret_key:
        errors.append("FLASK_SECRET_KEY is missing. Set it in your .env file.")
    elif len(secret_key) < 16 or secret_key.lower() in _PLACEHOLDER_SECRETS:
        errors.append("FLASK_SECRET_KEY is too short or still a placeholder (use 32+ random characters).")

    uri = (env.get("MONGODB_URI") or "").strip().strip('"').strip("'")
    if not uri:
        errors.append("MONGODB_URI is missing. Set it in your .env file.")
    elif not uri.startswith(("mongodb://", "mongodb+srv://")):
        errors.append(
            "MONGODB_URI must begin with 'mongodb://' or 'mongodb+srv://'. "
            "Check for stray quotes, spaces or a line break inside the value."
        )

    database = (env.get("MONGODB_DATABASE") or "career_copilot").strip()
    if not _DB_NAME_RE.match(database):
        errors.append("MONGODB_DATABASE may only contain letters, digits, '_' and '-' (max 63 chars).")

    timeout = _as_int(env, "MONGODB_TIMEOUT_MS", 10000, errors)
    max_upload = _as_int(env, "MAX_UPLOAD_MB", 5, errors)

    model = (env.get("GEMINI_MODEL") or "gemini-3.8-flash").strip()
    fallbacks_raw = env.get("GEMINI_FALLBACK_MODELS")
    if fallbacks_raw is None:
        fallbacks = Settings.gemini_fallback_models
    else:
        fallbacks = tuple(m.strip() for m in fallbacks_raw.split(",") if m.strip())

    if errors:
        raise ConfigError("Configuration problems:\n  - " + "\n  - ".join(errors))

    return Settings(
        secret_key=secret_key,
        mongodb_uri=uri,
        mongodb_database=database,
        mongodb_timeout_ms=timeout,
        mongodb_tls_ca_file=(env.get("MONGODB_TLS_CA_FILE") or "").strip() or None,
        gemini_api_key=(env.get("GEMINI_API_KEY") or "").strip() or None,
        gemini_model=model,
        gemini_fallback_models=fallbacks,
        max_upload_mb=max_upload,
        session_cookie_secure=_as_bool(env.get("SESSION_COOKIE_SECURE")),
        debug=_as_bool(env.get("FLASK_DEBUG")),
    )
