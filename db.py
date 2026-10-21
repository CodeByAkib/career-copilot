"""MongoDB Atlas connection helpers (PyMongo)."""
import re
import sys

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

from config import ConfigError, Settings, load_settings

USERS = "users"
REPORTS = "reports"


def mask_uri(text: str) -> str:
    """Hide the password in any mongodb URI contained in `text`."""
    return re.sub(r"(mongodb(?:\+srv)?://[^:/@\s]+:)[^@\s]+@", r"\1***@", text or "")


def create_client(settings: Settings) -> MongoClient:
    """Create a MongoClient. TLS certificate verification stays enabled."""
    options = {
        "serverSelectionTimeoutMS": settings.mongodb_timeout_ms,
        "connectTimeoutMS": settings.mongodb_timeout_ms,
        "appname": "career-copilot",
    }
    if settings.mongodb_tls_ca_file:
        options["tlsCAFile"] = settings.mongodb_tls_ca_file
    return MongoClient(settings.mongodb_uri, **options)


def ensure_indexes(database) -> None:
    """Create the indexes the app relies on (idempotent)."""
    database[USERS].create_index([("email", ASCENDING)], unique=True, name="uniq_email")
    database[REPORTS].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"
    )


def describe_error(exc: Exception) -> str:
    """One-line, secret-free description of a database error."""
    return f"{type(exc).__name__}: {mask_uri(str(exc))}"[:600]


def test_connection(settings: Settings) -> bool:
    client = create_client(settings)
    try:
        client.admin.command("ping")
        print(f"MongoDB connected. Database: {settings.mongodb_database}")
        return True
    except PyMongoError as exc:
        print("MongoDB connection FAILED:", describe_error(exc))
        print("Run `python check_mongo.py` for step-by-step diagnostics.")
        return False
    finally:
        client.close()


if __name__ == "__main__":
    try:
        sys.exit(0 if test_connection(load_settings()) else 1)
    except ConfigError as err:
        print(err)
        sys.exit(2)
