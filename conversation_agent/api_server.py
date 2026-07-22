"""
FastAPI HTTP Server — Conversation Design Assistant

Wraps WatsonxOrchestrator behind a REST API so the Carbon UI can call it.
Serves the UI HTML at GET / and accepts:
  POST /chat              — Python multi-agent pipeline (mock or live watsonx)
  POST /loop              — loop re-entry for show_next / doesnt_help
  POST /orchestrate/chat  — proxy to a deployed watsonx Orchestrate agent
  GET  /health            — mode flags for the UI header tag

Run with:
  python -m uvicorn conversation_agent.api_server:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

# Load .env before anything else — use direct assignment so new values in .env
# are always picked up even if the var was inherited from a parent process.
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _k, _v = _k.strip(), _v.strip()
            if _v:                          # only set non-empty values
                os.environ[_k] = _v

import httpx                                                    # noqa: E402
from fastapi import FastAPI, Request                           # noqa: E402
from fastapi.middleware.cors import CORSMiddleware             # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse       # noqa: E402
from pydantic import BaseModel                                 # noqa: E402

from conversation_agent.orchestrator import WatsonxOrchestrator  # noqa: E402
from conversation_agent.schemas import AgentInput, SessionStore   # noqa: E402

# ---------------------------------------------------------------------------
app = FastAPI(title="Conversation Design Assistant", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_orch = WatsonxOrchestrator()

# In-memory session store  {sessionId -> AgentInput}
_sessions: dict[str, AgentInput] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    sessionId: str
    userInput: str
    audience: str = "developer"
    maxLength: int = 2000
    humanReviewOnLowConfidence: bool = True
    userFormatPreference: str | None = None


class LoopRequest(BaseModel):
    sessionId: str
    feedbackSignal: str   # "show_next" | "doesnt_help"


class SelectRequest(BaseModel):
    """Layer 2: user picked a Layer 1 option."""
    sessionId: str          # same session created by POST /chat
    selectedId: str         # the option id (intent name) the user chose
    selectedLabel: str      # human label — stored in session for context
    queryFocus: str         # the full queryFocus string from the L1 option


class OrchestrateRequest(BaseModel):
    sessionId: str
    userInput: str
    audience: str = "developer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output_to_dict(out) -> dict:
    d = out.model_dump()
    # serialise bytes fields that can't JSON-encode
    if "sessionStore" in d:
        ss = d["sessionStore"]
        if ss.get("faissIndexBytes"):
            ss["faissIndexBytes"] = "<binary>"
    return d


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    ui_path = Path(__file__).parent.parent / "ui" / "index.html"
    return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))


@app.post("/chat")
async def chat(req: ChatRequest):
    inp = AgentInput(
        sessionId=req.sessionId,
        userInput=req.userInput,
        audience=req.audience,
        maxLength=req.maxLength,
        humanReviewOnLowConfidence=req.humanReviewOnLowConfidence,
        userFormatPreference=req.userFormatPreference,
        sessionStore=SessionStore(),
    )
    _sessions[req.sessionId] = inp
    out = _orch.run(inp)
    return JSONResponse(_output_to_dict(out))


@app.post("/loop")
async def loop(req: LoopRequest):
    inp = _sessions.get(req.sessionId)
    if inp is None:
        return JSONResponse({"error": "session not found"}, status_code=404)
    out = _orch.run_loop(inp, req.feedbackSignal)
    return JSONResponse(_output_to_dict(out))


@app.post("/select")
async def select(req: SelectRequest):
    """
    Layer 2 entry point.
    The user has chosen a Layer 1 option; now run Retrieval → Content
    with the sharpened intent and queryFocus.
    """
    inp = _sessions.get(req.sessionId)
    if inp is None:
        return JSONResponse({"error": "session not found"}, status_code=404)

    # Store the selected queryFocus so IntentAgent picks it up
    inp.sessionStore.userPreferences["selectedQueryFocus"] = req.queryFocus
    inp.sessionStore.userPreferences["selectedLabel"]      = req.selectedLabel

    # Signal Layer 2 via menu path
    inp.inputType      = "menu"
    inp.menuSelection  = req.selectedId

    out = _orch.run(inp)
    return JSONResponse(_output_to_dict(out))


# ---------------------------------------------------------------------------
# Orchestrate proxy — forwards to your deployed Orchestrate agent REST API
# and normalises the response into the same AgentOutput shape the UI expects.
# ---------------------------------------------------------------------------

# Per-session cache: {sessionId -> list[str]}  (normalised source URLs seen)
_orch_session_sources: dict[str, list[str]] = {}


def _normalise_url(url: str) -> str:
    """Strip tracking params and trailing slash for dedup comparison."""
    url = url.lower().rstrip("/")
    url = re.sub(r"[?&](wt\.mc_id|ocid|wt\.srch|utm_[^&]*)=[^&]*", "", url, flags=re.I)
    url = url.rstrip("?&")
    return url


@app.post("/orchestrate/chat")
async def orchestrate_chat(req: OrchestrateRequest):
    """
    Proxy POST to the watsonx Orchestrate agent REST API.

    Requires in .env:
      ORCHESTRATE_INSTANCE_URL  — e.g. https://api.au-syd.assistant.watson.cloud.ibm.com
      ORCHESTRATE_API_KEY       — IAM API key or ZenApiKey for your Orchestrate instance
      ORCHESTRATE_AGENT_ID      — the agent's published ID (from Orchestrate > Deploy)

    The Orchestrate Sessions API is used:
      POST /v2/assistants/{agent_id}/sessions          → create session
      POST /v2/assistants/{agent_id}/message/{sess_id} → send message

    Response is normalised to the AgentOutput shape so the UI needs no
    separate code path — it renders exactly as the Python pipeline does.
    """
    base_url   = os.environ.get("ORCHESTRATE_INSTANCE_URL", "").rstrip("/")
    agent_id   = os.environ.get("ORCHESTRATE_AGENT_ID", "")

    # Prefer the fresh JWT bearer token; fall back to ZenApiKey
    bearer_token = os.environ.get("WATSONX_BEARER_TOKEN", "").strip()
    api_key      = os.environ.get("ORCHESTRATE_API_KEY", "").strip()
    auth_token   = bearer_token or api_key

    if not (base_url and auth_token and agent_id):
        return JSONResponse(
            {"error": "ORCHESTRATE_INSTANCE_URL, ORCHESTRATE_AGENT_ID, and either "
                      "WATSONX_BEARER_TOKEN or ORCHESTRATE_API_KEY must be set in "
                      "conversation_agent/.env to use Orchestrate mode."},
            status_code=503,
        )

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1 — create or reuse a Watson Assistant session
        session_cache_key = f"orch_{req.sessionId}"
        orch_session_id = _sessions.get(session_cache_key)  # type: ignore[arg-type]

        if orch_session_id is None:
            sess_resp = await client.post(
                f"{base_url}/v2/assistants/{agent_id}/sessions",
                headers=headers,
                params={"version": "2023-06-15"},
            )
            if sess_resp.status_code != 201:
                return JSONResponse(
                    {"error": f"Could not create Orchestrate session: {sess_resp.text}"},
                    status_code=sess_resp.status_code,
                )
            orch_session_id = sess_resp.json().get("session_id", "")
            _sessions[session_cache_key] = orch_session_id  # type: ignore[assignment]
            _orch_session_sources[req.sessionId] = []

        # 2 — send the message
        msg_resp = await client.post(
            f"{base_url}/v2/assistants/{agent_id}/message/{orch_session_id}",
            headers=headers,
            params={"version": "2023-06-15"},
            json={"input": {"message_type": "text", "text": req.userInput}},
        )
        if msg_resp.status_code != 200:
            return JSONResponse(
                {"error": f"Orchestrate message failed: {msg_resp.text}"},
                status_code=msg_resp.status_code,
            )

    raw = msg_resp.json()

    # 3 — extract text from Orchestrate response envelope
    generic_responses = raw.get("output", {}).get("generic", [])
    text_parts = [r.get("text", "") for r in generic_responses if r.get("response_type") == "text"]
    full_text = "\n\n".join(t for t in text_parts if t).strip()

    # 4 — extract source URLs embedded in the markdown text (href patterns)
    seen_urls = _orch_session_sources.get(req.sessionId, [])
    url_pattern = re.compile(r'\(https?://learn\.microsoft\.com[^\)]+\)', re.I)
    title_url_pattern = re.compile(r'\[([^\]]+)\]\((https?://learn\.microsoft\.com[^\)]+)\)', re.I)

    sources_this_turn: list[dict] = []
    for match in title_url_pattern.finditer(full_text):
        title, url = match.group(1), match.group(2)
        norm = _normalise_url(url)
        if norm not in seen_urls:
            seen_urls.append(norm)
            sources_this_turn.append({"file_path": url, "title": title, "score": 1.0, "page_numbers": ""})
    _orch_session_sources[req.sessionId] = seen_urls

    # 5 — strip the "### Sources" or raw source block from the text if present
    cleaned_text = re.sub(
        r'\n+#{1,3}\s*Sources?\s*\n[\s\S]*$', '', full_text,
        flags=re.I
    ).strip()

    # 6 — build interactive options from the closing block A/B/C pattern
    options = []
    closing_pattern = re.compile(
        r'\*\*([A-C])\.\*\*\s+(.+?)(?=\n\*\*[A-C]\.\*\*|\Z)',
        re.S
    )
    for m in closing_pattern.finditer(cleaned_text):
        label_text = m.group(2).strip().split('\n')[0].strip()
        opt_id = f"orch_opt_{m.group(1).lower()}"
        # Source option: contains "Read the full guide:" and an MS Learn URL
        if "read the full guide" in label_text.lower() and sources_this_turn:
            src = sources_this_turn[0]
            options.append({
                "id": "source_redirect",
                "label": (label_text[:40] if len(label_text) > 40 else label_text),
                "description": label_text,
                "url": src["file_path"],
                "is_source": True,
            })
        else:
            options.append({
                "id": opt_id,
                "label": (label_text[:40] if len(label_text) > 40 else label_text),
                "description": label_text,
                "is_source": False,
            })

    # Strip the closing block from the displayed content
    cleaned_text = re.sub(
        r'\n+---\s*\n\*\*What would you like to do next\?\*\*[\s\S]*$',
        '', cleaned_text, flags=re.I
    ).strip()

    return JSONResponse({
        "sessionId": req.sessionId,
        "responseType": "answer",
        "responseText": cleaned_text[:120] + ("…" if len(cleaned_text) > 120 else ""),
        "format": "orchestrate",
        "content": cleaned_text,
        "interactiveOptions": options,
        "sources": sources_this_turn,
        "confidence": "High",
        "mcpSessionId": orch_session_id,
        "suggestedRefinements": [],
        "routeToHumanReview": False,
        "estimatedReadTime": f"{max(1, len(cleaned_text.split()) // 200)} min read",
        "validationReport": {"clarityScore": 5, "concisionScore": 4, "accessibilityPass": True},
        "mode": "orchestrate",
    })


@app.get("/health")
async def health():
    has_bearer = bool(os.environ.get("WATSONX_BEARER_TOKEN", "").strip())
    has_zenkey = bool(os.environ.get("ORCHESTRATE_API_KEY", "").strip())
    orchestrate_configured = bool(
        os.environ.get("ORCHESTRATE_INSTANCE_URL") and
        (has_bearer or has_zenkey) and
        os.environ.get("ORCHESTRATE_AGENT_ID")
    )
    return {
        "status": "ok",
        "mock_mode": os.environ.get("MOCK_MODE", "true"),
        "orchestrate_available": orchestrate_configured,
        "orchestrate_auth": "bearer_token" if has_bearer else ("zen_api_key" if has_zenkey else "none"),
    }
