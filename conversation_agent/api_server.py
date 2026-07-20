"""
FastAPI HTTP Server — Conversation Design Assistant

Wraps WatsonxOrchestrator behind a REST API so the Carbon UI can call it.
Serves the UI HTML at GET / and accepts POST /chat and POST /loop.

Run with:
  python -m uvicorn conversation_agent.api_server:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Load .env before anything else
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

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


@app.get("/health")
async def health():
    return {"status": "ok", "mock_mode": os.environ.get("MOCK_MODE", "true")}
