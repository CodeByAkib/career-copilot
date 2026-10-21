"""Step-by-step MongoDB Atlas connectivity diagnostics.

Usage (PowerShell, venv active):  python check_mongo.py

Separates configuration, DNS, TCP, TLS and PyMongo-level problems so you can tell whether
the fault is in this app, on your network, or on the Atlas side. Passwords are never printed.
"""
import os
import socket
import ssl
import sys
from urllib.parse import parse_qs, unquote, urlsplit

import certifi
import dns.resolver
import pymongo
from dotenv import dotenv_values, load_dotenv

from db import describe_error, mask_uri

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def line(tag, msg):
    print(f"{tag} {msg}")


def check_env():
    os_value = os.environ.get("MONGODB_URI")
    file_value = dotenv_values(".env").get("MONGODB_URI") if os.path.exists(".env") else None
    if not os.path.exists(".env"):
        line(WARN, ".env file not found in the current directory (%s)." % os.getcwd())
    if os_value and file_value and os_value.strip() != file_value.strip():
        line(BAD, "A MONGODB_URI environment variable set in this PowerShell session/Windows differs from "
                  "the one in .env. python-dotenv does NOT override it, so the app uses the OLD value. "
                  "Fix: Remove-Item Env:MONGODB_URI   (and delete it from Windows environment variables if set there)")
    load_dotenv()
    uri = (os.environ.get("MONGODB_URI") or "").strip()
    if not uri:
        line(BAD, "MONGODB_URI is not set.")
        return None
    if uri != uri.strip("\"'"):
        line(BAD, "MONGODB_URI is wrapped in quotes; remove them in .env.")
    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        line(BAD, "MONGODB_URI does not start with mongodb:// or mongodb+srv://")
        return None
    parts = urlsplit(uri)
    line(OK, f"URI parsed: scheme={parts.scheme} user={unquote(parts.username or '') or '(none)'} "
             f"password={'set' if parts.password else 'MISSING'} host={parts.hostname} "
             f"options={dict(parse_qs(parts.query))}")
    if parts.password and any(c in parts.password for c in "@/?#[]"):
        line(BAD, "Password contains unescaped special characters; percent-encode them (e.g. @ -> %40).")
    return uri


def resolve_hosts(uri):
    parts = urlsplit(uri)
    if parts.scheme == "mongodb":
        hosts = [h for h in parts.netloc.rsplit("@", 1)[-1].split(",")]
        return [(h.split(":")[0], int(h.split(":")[1]) if ":" in h else 27017) for h in hosts]
    name = f"_mongodb._tcp.{parts.hostname}"
    try:
        answers = dns.resolver.resolve(name, "SRV")
    except Exception as exc:
        line(BAD, f"SRV lookup for {name} failed: {type(exc).__name__}: {exc}")
        line(WARN, "If your DNS server blocks SRV records try: set DNS to 8.8.8.8/1.1.1.1, a phone hotspot, "
                   "or use the non-SRV 'standard connection string' from Atlas.")
        return []
    hosts = sorted((str(a.target).rstrip("."), a.port) for a in answers)
    line(OK, f"SRV lookup returned {len(hosts)} member(s): " + ", ".join(f"{h}:{p}" for h, p in hosts))
    return hosts


def check_tls(host, port):
    """TCP connect + verified TLS handshake for one replica-set member."""
    try:
        sock = socket.create_connection((host, port), timeout=8)
    except Exception as exc:
        line(BAD, f"{host}:{port} TCP connect failed: {type(exc).__name__}: {exc} (firewall/Network Access/VPN?)")
        return False
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            line(OK, f"{host}:{port} TCP+TLS verified ({tls.version()}, {tls.cipher()[0]})")
            return True
    except ssl.SSLError as exc:
        line(BAD, f"{host}:{port} TLS handshake failed: {exc}")
        return False
    except Exception as exc:
        line(BAD, f"{host}:{port} TLS error: {type(exc).__name__}: {exc}")
        return False
    finally:
        sock.close()


def check_pymongo(uri):
    client = None
    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=15000, appname="career-copilot-diag")
        client.admin.command("ping")
        line(OK, "PyMongo ping succeeded (authenticated, primary available).")
        return True
    except Exception as exc:
        line(BAD, "PyMongo ping failed: " + describe_error(exc))
        return False
    finally:
        if client is not None:
            client.close()


def main():
    print(f"Python {sys.version.split()[0]} | {ssl.OPENSSL_VERSION} | PyMongo {pymongo.version}\n")
    print("1) Configuration")
    uri = check_env()
    if not uri:
        return 2
    print("\n2) DNS")
    hosts = resolve_hosts(uri)
    print("\n3) TCP + TLS per member")
    results = [check_tls(h, p) for h, p in hosts]
    print("\n4) PyMongo")
    ok = check_pymongo(uri)
    print("\nInterpretation")
    if ok:
        line(OK, "Atlas is reachable and authenticated from this machine.")
        return 0
    if not hosts:
        line(WARN, "DNS/SRV resolution failed, so no connection was attempted: check the cluster hostname "
                   "in MONGODB_URI (copy it again from Atlas) and your DNS/VPN settings.")
    elif results and not any(results):
        line(WARN, "No member accepted a TLS handshake: usually Atlas Network Access (your current public IP "
                   "is not on the IP Access List), a paused cluster, VPN/proxy/antivirus HTTPS scanning, or a firewall.")
    elif results and not all(results):
        line(WARN, "Some members work and some fail: typically an Atlas-side issue (a node restarting, "
                   "failover/election in progress, maintenance) or an IP Access List problem. "
                   "Check the cluster status/Metrics in the Atlas UI and retry in a few minutes.")
    elif results and all(results):
        line(WARN, "TCP+TLS works for every member but PyMongo failed: check the database user/password "
                   "(Database Access), the 'authSource', and the cluster's replica-set state in Atlas.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
