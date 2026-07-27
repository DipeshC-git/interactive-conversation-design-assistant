# -*- coding: utf-8 -*-
"""
Flask server — Conversation Design Assistant
============================================
Serves the Watson Orchestrate chat embed.

Routes
------
GET  /        Serve ui2.html (no-cache)
GET  /config  Credentials JSON consumed by ui2.html to boot the SDK
GET  /health  Liveness check
"""

import os
import re
import time
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

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
                    os.environ.setdefault(_k, _v)
        break

# ---------------------------------------------------------------------------
# Credentials — all read from .env
# ---------------------------------------------------------------------------

HOST_URL = os.environ.get("HOST_URL", "https://dl.watson-orchestrate.ibm.com").rstrip("/")
ORCHESTRATION_ID = os.environ.get("ORCHESTRATION_ID", "")
AGENT_ID = os.environ.get("ORCHESTRATE_AGENT_ID", "")
AGENT_ENV_ID = os.environ.get("AGENT_ENV_ID", "")

UI_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
app = Flask(__name__)


# ===========================================================================
# ROUTES
# ===========================================================================

@app.route("/")
def index():
    resp = send_from_directory(UI_DIR, "ui2.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp


@app.route("/config")
def config():
    missing = [k for k, v in [
        ("ORCHESTRATE_AGENT_ID", AGENT_ID),
        ("AGENT_ENV_ID",         AGENT_ENV_ID),
        ("ORCHESTRATION_ID",     ORCHESTRATION_ID),
    ] if not v]
    if missing:
        return jsonify({"error": f"Missing required .env keys: {', '.join(missing)}"}), 503
    return jsonify({
        "host_url"        : HOST_URL,
        "orchestration_id": ORCHESTRATION_ID,
        "agent_id"        : AGENT_ID,
        "agent_env_id"    : AGENT_ENV_ID,
        "build_ts"        : str(int(time.time())),
    })


@app.get("/health")
def health():
    return jsonify({
        "status"          : "ok",
        "host_url"        : HOST_URL,
        "agent_id"        : AGENT_ID,
        "orchestration_id": ORCHESTRATION_ID,
    })


if __name__ == "__main__":
    print("=" * 60)
    print("Conversation Design Assistant")
    print(f"  SDK host  : {HOST_URL}")
    print(f"  agent_id  : {AGENT_ID}")
    print(f"  env_id    : {AGENT_ENV_ID}")
    print(f"  orch_id   : {ORCHESTRATION_ID}")
    print(f"  open      : http://localhost:5001")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
