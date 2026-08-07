# -*- coding: utf-8 -*-
"""
Flask server — Intently
============================================
Serves the Watson Orchestrate chat embed.

Routes
------
GET  /           Serve ui.html (no-cache)
GET  /config     Credentials JSON consumed by ui.html to boot wxoLoader
GET  /api/token  Exchange IAM API key for bearer token (cached, used by authTokenNeeded)
GET  /health     Liveness check
"""

import os
import re
import time
from pathlib import Path

import requests as _requests
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Load .env (this directory first, then project root)
# ---------------------------------------------------------------------------
for _candidate in (Path(__file__).parent / ".env",
                   Path(__file__).parent.parent / ".env"):
    if _candidate.exists():
        for _line in _candidate.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip()
                if _v:
                    os.environ[_k] = _v      # set non-empty values
                else:
                    os.environ.pop(_k, None)  # empty value in .env → clear the var
        break


# ---------------------------------------------------------------------------
# IAM token cache
# ---------------------------------------------------------------------------

_token_cache: dict = {}   # keys: token, expiry


def _get_bearer_token() -> tuple[str, str]:
    """
    Return (bearer_token, error_message).
    Exchanges ORCHESTRATE_API_KEY / WATSONX_IAM_APIKEY for an IAM bearer token.
    Caches the token until 5 minutes before expiry.
    """
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expiry", 0) > now:
        return _token_cache["token"], ""

    iam_apikey = (os.environ.get("ORCHESTRATE_API_KEY", "").strip()
                  or os.environ.get("WATSONX_IAM_APIKEY", "").strip())
    if not iam_apikey:
        return "", "ORCHESTRATE_API_KEY or WATSONX_IAM_APIKEY not set"

    try:
        resp = _requests.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                  "apikey": iam_apikey},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token  = data.get("access_token", "")
        expiry = now + data.get("expires_in", 3600) - 300   # 5-min buffer
        _token_cache["token"]  = token
        _token_cache["expiry"] = expiry
        return token, ""
    except Exception as e:
        return "", str(e)


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def _derive_crn(host_url: str, orchestration_id: str) -> str:
    """Derive CRN from hostURL + orchestrationID."""
    if not host_url or not orchestration_id or "_" not in orchestration_id:
        return ""
    region_match = re.match(r'https?://([^.]+)\.watson-orchestrate', host_url)
    if not region_match:
        return ""
    region = region_match.group(1)
    account_id, instance_id = orchestration_id.split("_", 1)
    return f"crn:v1:bluemix:public:watsonx-orchestrate:{region}:a/{account_id}:{instance_id}::"


def _credentials():
    """Read credentials fresh from os.environ each call."""
    host_url         = os.environ.get("HOST_URL", "").rstrip("/")
    orchestration_id = os.environ.get("ORCHESTRATION_ID", "")
    crn              = os.environ.get("WXO_CRN", "") or _derive_crn(host_url, orchestration_id)
    iam_apikey       = (os.environ.get("ORCHESTRATE_API_KEY", "").strip()
                        or os.environ.get("WATSONX_IAM_APIKEY", "").strip())
    return {
        "host_url"        : host_url,
        "orchestration_id": orchestration_id,
        "crn"             : crn,
        "iam_apikey"      : iam_apikey,
        "agent_id"        : os.environ.get("ORCHESTRATE_AGENT_ID", ""),
        "agent_env_id"    : os.environ.get("AGENT_ENV_ID", ""),
    }


# ---------------------------------------------------------------------------
# CORS — Code Engine production URL + localhost for local dev
_PRODUCTION_URL = os.environ.get(
    "APP_URL",
    "https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud",
)
_LOCAL_ORIGINS = [
    "http://localhost:5001",
    "http://127.0.0.1:5001",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_extra = [o.strip() for o in os.environ.get("APP_EXTRA_ORIGINS", "").split(",") if o.strip()]
_ALLOWED_ORIGINS = [_PRODUCTION_URL] + _LOCAL_ORIGINS + _extra

UI_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
CORS(app, origins=_ALLOWED_ORIGINS)


# ===========================================================================
# ROUTES
# ===========================================================================

@app.route("/")
def index():
    resp = send_from_directory(UI_DIR, "ui.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp


@app.route("/config")
def config():
    creds = _credentials()
    missing = [k for k, v in [
        ("HOST_URL",           creds["host_url"]),
        ("ORCHESTRATION_ID",   creds["orchestration_id"]),
        ("ORCHESTRATE_AGENT_ID", creds["agent_id"]),
        ("AGENT_ENV_ID",       creds["agent_env_id"]),
    ] if not v]
    if missing:
        return jsonify({"error": f"Missing required .env keys: {', '.join(missing)}"}), 503
    return jsonify({**creds, "build_ts": str(int(time.time()))})


@app.get("/api/token")
def api_token():
    """
    Called by ui.html's authTokenNeeded handler.
    Returns {token} — a fresh IAM bearer token.
    """
    token, err = _get_bearer_token()
    if err:
        return jsonify({"error": err}), 503
    return jsonify({"token": token})


@app.get("/health")
def health():
    creds = _credentials()
    return jsonify({
        "status"          : "ok",
        "host_url"        : creds["host_url"],
        "orchestration_id": creds["orchestration_id"],
        "agent_id"        : creds["agent_id"],
        "iam_key_set"     : bool(creds["iam_apikey"]),
    })


if __name__ == "__main__":
    creds = _credentials()
    port  = int(os.environ.get("PORT", 5001))
    print("=" * 60)
    print("Intently")
    print(f"  host_url  : {creds['host_url']}")
    print(f"  orch_id   : {creds['orchestration_id']}")
    print(f"  agent_id  : {creds['agent_id']}")
    print(f"  open      : http://localhost:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
