"""
orchestrate_client.py
─────────────────────
Service layer for Watson Orchestrate SaaS native REST API.

Instance URL:   https://<region>.dl.watson-orchestrate.ibm.com
API path:       POST /api/v1/agents/{agent_id}/chat
Auth:           Bearer <session-jwt>  (short-lived, ~15 min)

The session JWT is obtained by logging into Watson Orchestrate in a browser
and copying it from DevTools (F12 -> Network -> any /api/v1/... request ->
Authorization header -> value after "Bearer ").

Environment variables (set in conversation_agent/.env):

  ORCHESTRATE_INSTANCE_URL  — e.g. https://ap-south-1.dl.watson-orchestrate.ibm.com
  ORCHESTRATE_AGENT_ID      — Agent ID shown in Orchestrate > your agent > Settings/Deploy
  WATSONX_BEARER_TOKEN      — Session JWT from browser DevTools (expires ~15 min)

How to refresh WATSONX_BEARER_TOKEN:
  1. Open Watson Orchestrate in Chrome/Edge.
  2. Press F12 -> Network tab -> filter by /api/v1/.
  3. Send any message to your agent or refresh the page.
  4. Click any request -> Headers -> copy the Authorization header value
     (the part AFTER "Bearer ").
  5. Paste into WATSONX_BEARER_TOKEN= in conversation_agent/.env.
  6. Click "Clear conversation" in the app sidebar (re-reads .env automatically).
"""

from __future__ import annotations

import os
import time
import base64
import json
import logging
from typing import Optional

import requests
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=_env_path, override=True)

logger = logging.getLogger(__name__)


def _get_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Environment variable '{key}' is not set. "
            "Add it to conversation_agent/.env."
        )
    return value


def _jwt_expiry(token: str) -> Optional[float]:
    """Decode 'exp' from a JWT payload without verifying the signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.b64decode(padded))
        return float(payload.get("exp", 0))
    except Exception:
        return None


def _read_env_file_direct(key: str) -> str:
    """
    Read a single key directly from the .env file on disk, bypassing os.environ.
    This guarantees the latest value is used even inside a long-running process
    where os.environ still holds a stale value from an earlier load.
    """
    try:
        with open(_env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    except Exception:
        pass
    return ""


def _get_bearer_token() -> str:
    """
    Return the Bearer JWT from WATSONX_BEARER_TOKEN.
    Reads directly from the .env file on disk every call — so pasting a new token
    into .env is picked up immediately without restarting Streamlit.
    """
    # Read directly from disk — bypasses the stale os.environ cache
    raw = _read_env_file_direct("WATSONX_BEARER_TOKEN")
    # Fall back to os.environ if not in file
    if not raw:
        raw = os.getenv("WATSONX_BEARER_TOKEN", "").strip()

    if not raw:
        raise EnvironmentError(
            "WATSONX_BEARER_TOKEN is not set.\n"
            "To get a token:\n"
            "  1. Open Watson Orchestrate in Chrome/Edge.\n"
            "  2. Press F12 -> Network tab.\n"
            "  3. Send any message to your agent.\n"
            "  4. Click any /api/v1/ request -> Headers -> copy the Authorization value.\n"
            "  5. Paste into WATSONX_BEARER_TOKEN= in conversation_agent/.env.\n"
            "  6. Click 'Clear conversation' in the sidebar."
        )

    token = raw[7:] if raw.lower().startswith("bearer ") else raw
    exp = _jwt_expiry(token)
    if exp is not None and exp < time.time():
        ago_min = int((time.time() - exp) / 60)
        raise EnvironmentError(
            f"WATSONX_BEARER_TOKEN expired {ago_min} min ago.\n"
            "To refresh:\n"
            "  1. Open Watson Orchestrate in Chrome/Edge.\n"
            "  2. Press F12 -> Network tab.\n"
            "  3. Send any message to your agent.\n"
            "  4. Click any /api/v1/ request -> Headers -> copy the Authorization value\n"
            "     (the full value after 'Bearer ').\n"
            "  5. Paste into WATSONX_BEARER_TOKEN= in .env.\n"
            "  6. Click 'Clear conversation' in the sidebar to re-read the token."
        )

    return token


# ─────────────────────────────────────────────────────────────────────────────
# OrchestrateClient  — native /api/v1/agents/{id}/chat endpoint
# ─────────────────────────────────────────────────────────────────────────────

class OrchestrateClient:
    """
    Client for the Watson Orchestrate SaaS native REST API.

    Uses a stateless POST /api/v1/agents/{agent_id}/chat — no session creation
    needed. Each call sends the conversation history (maintained in session_state)
    together with the new user message.

    Lifecycle:
      client = OrchestrateClient()
      reply  = client.chat("Hello")         # first turn
      reply  = client.chat("Follow-up")     # subsequent turns carry history
      client.reset()                        # clear local history
    """

    def __init__(self) -> None:
        self.instance_url: str = _get_env("ORCHESTRATE_INSTANCE_URL").rstrip("/")
        self.agent_id: str = _get_env("ORCHESTRATE_AGENT_ID")
        self._history: list[dict] = []   # [{role, content}, ...]

    @property
    def session_id(self) -> Optional[str]:
        """Compatibility shim — stateless API has no session ID."""
        return "native-api" if self._history else None

    def create_session(self) -> str:
        """No-op shim for API compatibility — native API is stateless."""
        self._history = []
        return "native-api"

    def delete_session(self) -> None:
        """Reset local history."""
        self._history = []

    def send_message(self, user_text: str) -> str:
        """
        POST /api/v1/agents/{agent_id}/chat

        Sends user_text (with conversation history) to the live Orchestrate agent
        and returns the agent's reply text.
        """
        token = _get_bearer_token()
        self._history.append({"role": "user", "content": user_text})

        url = f"{self.instance_url}/api/v1/agents/{self.agent_id}/chat"
        payload = {
            "input": user_text,
            "history": self._history[:-1],   # history before current message
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            self._history.pop()  # remove the user turn on failure
            _raise_api_error("chat", exc)
        except requests.exceptions.ConnectionError:
            self._history.pop()
            raise ConnectionError(
                f"Cannot reach Orchestrate at {self.instance_url}.\n"
                "Check ORCHESTRATE_INSTANCE_URL in .env."
            )

        reply = _extract_text(resp.json())
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self._history = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def _raise_api_error(operation: str, exc: requests.exceptions.HTTPError) -> None:
    resp = exc.response
    status = resp.status_code if resp is not None else "?"
    body = ""
    if resp is not None:
        try:
            j = resp.json()
            body = j.get("message", j.get("error", resp.text))
        except Exception:
            body = resp.text

    hints: list[str] = []
    if status == 401:
        bt = os.getenv("WATSONX_BEARER_TOKEN", "").strip()
        token = bt[7:] if bt.lower().startswith("bearer ") else bt
        exp = _jwt_expiry(token) if bt else None
        if exp and exp < time.time():
            ago_min = int((time.time() - exp) / 60)
            hints.append(f"Token expired {ago_min} min ago.")
        else:
            hints.append("Session token rejected.")
        hints += [
            "To refresh WATSONX_BEARER_TOKEN:",
            "  1. Open Watson Orchestrate in Chrome/Edge.",
            "  2. Press F12 -> Network tab.",
            "  3. Send any message to your agent.",
            "  4. Click any /api/v1/ request -> Headers -> copy the Authorization value.",
            "  5. Paste into WATSONX_BEARER_TOKEN= in .env.",
            "  6. Click 'Clear conversation' in the sidebar.",
        ]
    elif status == 404:
        hints = [
            "Agent not found.",
            "Check ORCHESTRATE_AGENT_ID and ORCHESTRATE_INSTANCE_URL in .env.",
        ]

    hint_str = "\n".join(hints)
    raise RuntimeError(
        f"Orchestrate API error [{status}]: {body}\n{hint_str}"
    ) from exc


def _extract_text(response_body: dict) -> str:
    """
    Extract the reply text from the Orchestrate /api/v1/agents/{id}/chat response.

    Orchestrate native chat response shape (varies by agent):
      { "output": "text" }
      { "output": { "text": "..." } }
      { "response": "text" }
      { "message": "text" }
      { "result": "text" }
      Watson Assistant v2 compatible: output.generic[].text
    """
    try:
        # Native Orchestrate API shapes
        out = response_body.get("output")
        if isinstance(out, str) and out:
            return out
        if isinstance(out, dict):
            t = out.get("text") or out.get("message") or out.get("response")
            if t:
                return str(t)
            # Watson Assistant v2 style
            generics = out.get("generic", [])
            parts = [
                item["text"]
                for item in generics
                if item.get("response_type") == "text" and item.get("text")
            ]
            if parts:
                return "\n\n".join(parts)

        # Other common shapes
        for field in ("response", "message", "result", "text", "answer"):
            v = response_body.get(field)
            if isinstance(v, str) and v:
                return v

        # Last resort — dump the JSON so the user sees something
        return f"(Unexpected response shape — raw: {json.dumps(response_body)[:400]})"

    except Exception as exc:
        logger.warning("Failed to parse response body: %s", exc)
        return "(Could not parse the agent response.)"
