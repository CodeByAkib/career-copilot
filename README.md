# AI Career Copilot

Flask app that analyses a resume (pasted text, PDF or DOCX) against a target job role using Google Gemini,
stores each report in MongoDB Atlas and shows a per-user history.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Flask app factory, routes, CSRF/security headers, error handlers |
| `config.py` | Reads/validates environment variables (`.env`) |
| `db.py` | PyMongo client, indexes, `python db.py` connection test |
| `models.py` / `validation.py` | Document builders / input validation |
| `resume_parser.py` | PDF & DOCX text extraction (in memory, nothing saved to disk) |
| `ai.py` | Gemini call, JSON parsing, schema normalisation |
| `check_mongo.py`, `check_gemini.py` | Diagnostics (see Troubleshooting) |
| `tests/` | Automated tests (mocked Gemini + `mongomock`, no credentials needed) |

## Windows setup (PowerShell)

1. **Python** – install Python 3.11–3.13 from python.org (tick *Add python.exe to PATH*). Check: `python --version`
2. **Virtual environment**
   ```powershell
   cd "C:\Career Copilot"
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
   (Your old `venv` contains the removed MySQL/SQLAlchemy packages; creating a fresh one is cleanest:
   `Remove-Item -Recurse -Force venv` first.)
3. **Dependencies**
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. **MongoDB Atlas cluster** – <https://cloud.mongodb.com> → create a project → *Build a Database* (free M0 is fine).
5. **Database user** – *Security → Database Access → Add New Database User* (password auth, role *Read and write to any database*).
   Prefer a password with only letters/digits; otherwise URL-encode special characters (`@` → `%40`).
6. **Network access** – *Security → Network Access → Add IP Address → Add Current IP Address*.
   Your IP changes on most home/mobile connections; if it does, add the new one. Find your public IP with
   `Invoke-RestMethod https://api.ipify.org`. (`0.0.0.0/0` allows everyone and is not recommended beyond quick tests.)
7. **Environment variables**
   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
   - `MONGODB_URI`: Atlas → *Connect → Drivers* → copy the `mongodb+srv://…` string, replace `<db_password>`.
   - `FLASK_SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`
   - One `KEY=value` per line, no quotes, no spaces around `=`.
   - Make sure no stale `MONGODB_URI` exists in your session: `Remove-Item Env:MONGODB_URI -ErrorAction SilentlyContinue`
     (real environment variables win over `.env`).
8. **Gemini key** – create a key at <https://aistudio.google.com/apikey> and put it in `GEMINI_API_KEY`.
   Then run `python check_gemini.py` to confirm the key works and which model to use (`GEMINI_MODEL`).
9. **Test MongoDB connectivity**
   ```powershell
   python check_mongo.py     # detailed step-by-step diagnosis
   python db.py              # quick ping
   ```
10. **Run the app**
    ```powershell
    python app.py
    ```
    Open <http://127.0.0.1:5000>. The app starts even if Atlas is unreachable (pages needing the database show a
    "Database unavailable" message and the reason is logged without credentials).
11. **Run the tests**
    ```powershell
    pip install -r requirements-dev.txt
    python -m pytest -q
    ```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `InvalidURI: URI must begin with 'mongodb://'…` | Malformed `MONGODB_URI` (quotes, line break, stale OS env var). Run `python check_mongo.py`. |
| `ServerSelectionTimeoutError … ReplicaSetNoPrimary` with some hosts `RSSecondary` and one TLS `TLSV1_ALERT_INTERNAL_ERROR` | **Not an application bug.** The driver reached some members but found no primary. Check in Atlas: cluster status (paused / resuming / maintenance / failover), *Network Access* contains your current IP, and wait a few minutes. Then run `python check_mongo.py` to see which member fails. Also try another network (phone hotspot), disable VPN/proxy, and exclude HTTPS scanning in antivirus. Never disable TLS verification. |
| `Authentication failed` | Wrong database user/password (Atlas → Database Access) or un-encoded special characters. |
| Gemini `401/403 / API key not valid` | Key invalid or restricted. New `AQ.…` keys have been reported to fail with some libraries; if `check_gemini.py` fails, create a key in Google Cloud Console (APIs & Services → Credentials) restricted to the Generative Language API. |
| Gemini `404 model not found` | Set `GEMINI_MODEL` to a model listed by `python check_gemini.py`. |
| `FLASK_SECRET_KEY …` / `MONGODB_URI …` config error | Fill in `.env` (copy from `.env.example`). |

## Production notes

- Set `FLASK_DEBUG=0` (default), `SESSION_COOKIE_SECURE=1` and serve over HTTPS (reverse proxy).
- Don't use `python app.py`; use a WSGI server, e.g. on Windows `pip install waitress` then
  `waitress-serve --call app:create_app`.
- Provide secrets via real environment variables or a secret manager, not a committed `.env`.
- Restrict Atlas Network Access to your server's IP(s); use a dedicated least-privilege DB user.
- Add login rate limiting (e.g. Flask-Limiter with Redis) – not included.
- Uploads are parsed in memory and never written to disk; resume text of each analysis is stored in the `reports` collection – tell users and add deletion if needed.
