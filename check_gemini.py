"""Check the Gemini API key and model.  Usage: python check_gemini.py"""
import sys

from config import ConfigError, load_settings


def main():
    try:
        settings = load_settings()
    except ConfigError as err:
        print(err)
        return 2
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set in .env")
        return 2

    from google import genai
    client = genai.Client(api_key=settings.gemini_api_key)
    print(f"Configured model: {settings.gemini_model} (fallbacks: {', '.join(settings.gemini_fallback_models) or 'none'})")
    try:
        names = sorted(m.name.replace("models/", "") for m in client.models.list()
                       if "generateContent" in (getattr(m, "supported_actions", None) or ["generateContent"]))
        print(f"Models available to this key ({len(names)}):", ", ".join(n for n in names if "gemini" in n)[:1500])
        if settings.gemini_model not in names:
            print(f"WARNING: {settings.gemini_model} is not in that list. Set GEMINI_MODEL to one of them.")
    except Exception as exc:
        print("Could not list models:", type(exc).__name__, getattr(exc, "code", ""))

    try:
        reply = client.models.generate_content(model=settings.gemini_model, contents="Reply with the single word: ok")
        print("Test call succeeded:", (reply.text or "").strip()[:40])
        return 0
    except Exception as exc:
        print("Test call FAILED:", type(exc).__name__, "code =", getattr(exc, "code", "?"))
        print("401/403 -> key invalid/restricted (new 'AQ.' keys: see README). 404 -> change GEMINI_MODEL. 429 -> quota.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
