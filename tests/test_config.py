import pytest

from config import ConfigError, load_settings

GOOD = {"FLASK_SECRET_KEY": "s" * 40, "MONGODB_URI": "mongodb+srv://u:p@c.example.net/?retryWrites=true"}


def test_valid_config():
    s = load_settings(GOOD, load_env_file=False)
    assert s.mongodb_database == "career_copilot" and s.gemini_api_key is None and not s.debug


def test_missing_values_listed_together():
    with pytest.raises(ConfigError) as exc:
        load_settings({}, load_env_file=False)
    assert "FLASK_SECRET_KEY" in str(exc.value) and "MONGODB_URI" in str(exc.value)


def test_malformed_uri_rejected_without_leaking_value():
    env = dict(GOOD, MONGODB_URI="mongo://user:topsecret@host")
    with pytest.raises(ConfigError) as exc:
        load_settings(env, load_env_file=False)
    assert "mongodb+srv://" in str(exc.value) and "topsecret" not in str(exc.value)


def test_quoted_uri_is_unwrapped():
    s = load_settings(dict(GOOD, MONGODB_URI='"mongodb://localhost"'), load_env_file=False)
    assert s.mongodb_uri == "mongodb://localhost"


def test_placeholder_secret_and_bad_numbers():
    with pytest.raises(ConfigError) as exc:
        load_settings(dict(GOOD, FLASK_SECRET_KEY="change-me", MAX_UPLOAD_MB="abc"), load_env_file=False)
    assert "FLASK_SECRET_KEY" in str(exc.value) and "MAX_UPLOAD_MB" in str(exc.value)


def test_model_fallbacks_parse():
    s = load_settings(dict(GOOD, GEMINI_MODEL="m1", GEMINI_FALLBACK_MODELS="a, b"), load_env_file=False)
    assert s.gemini_model == "m1" and s.gemini_fallback_models == ("a", "b")


def test_mask_uri():
    from db import mask_uri
    assert "hunter2" not in mask_uri("failed mongodb+srv://bob:hunter2@host/x")
