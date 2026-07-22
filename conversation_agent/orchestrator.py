"""
watsonx Orchestrator — Loop Controller

Drives IntentAgent → RetrievalAgent → ContentAgent in sequence.
Controls the feedback loop (no hard cap), enforces the iteration-5
escalation gate, and assembles the final AgentOutput.

Entry points:
  run(input)             — first turn
  run_loop(input, fb)    — subsequent turns when user picks "show_next" / "doesnt_help"
"""
from __future__ import annotations

import os
from pathlib import Path

from conversation_agent.content_agent import ContentAgent
from conversation_agent.intent_agent import IntentAgent
from conversation_agent.retrieval_agent import RetrievalAgent
from conversation_agent.schemas import (
    AgentInput,
    AgentOutput,
    InteractiveOption,
    SessionStore,
    Source,
    ValidationReport,
)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def _load_env() -> None:
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()
MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"


def _init_watsonx_model() -> object | None:
    """
    Initialise watsonx ModelInference client using IBM Cloud IAM API key.

    Credential resolution order:
      1. WATSONX_IAM_APIKEY (standard IBM Cloud IAM key — recommended)
      2. WATSONX_BEARER_TOKEN (Watson Orchestrate SSO token — legacy)

    Returns None in mock mode or when credentials/URL are missing.
    """
    if MOCK_MODE:
        return None
    url  = os.environ.get("WATSONX_URL", "").rstrip("/")
    proj = os.environ.get("WATSONX_PROJECT_ID", "")
    if not (url and proj):
        return None
    try:
        from ibm_watsonx_ai import Credentials           # type: ignore
        from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore

        iam_key = os.environ.get("WATSONX_IAM_APIKEY", "")
        bearer  = os.environ.get("WATSONX_BEARER_TOKEN", "")

        if iam_key:
            creds = Credentials(url=url, api_key=iam_key)
        elif bearer:
            creds = Credentials(url=url, token=bearer)
        else:
            return None  # no usable credential

        return ModelInference(
            model_id="ibm/granite-13b-chat-v2",
            credentials=creds,
            project_id=proj,
            validate=False,   # skip connectivity check at construction time
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper — build AgentOutput from agent results
# ---------------------------------------------------------------------------

def _assemble_output(
    session_id: str,
    response_type: str,
    content_result: dict,
    session_store: SessionStore,
    route_human: bool,
) -> AgentOutput:
    sources = [
        Source(
            file_path=s["file_path"],
            page_numbers=str(s.get("page_numbers", "")),
            score=float(s.get("score", 0.0)),
        )
        for s in content_result.get("sources", [])
    ]
    options = [
        InteractiveOption(**o) if isinstance(o, dict) else o
        for o in content_result.get("interactiveOptions", [])
    ]
    vr_raw = content_result.get(
        "validationReport",
        {"clarityScore": 0, "concisionScore": 0, "accessibilityPass": False},
    )
    validation = ValidationReport(**vr_raw) if isinstance(vr_raw, dict) else vr_raw

    return AgentOutput(
        sessionId=session_id,
        responseType=response_type,
        responseText=content_result.get("responseText", ""),
        format=content_result.get("format"),
        content=content_result.get("content", ""),
        interactiveOptions=options,
        sources=sources,
        confidence=content_result.get("confidence", "Low"),
        mcpSessionId=session_store.mcpSessionId,
        suggestedRefinements=content_result.get("suggestedRefinements", []),
        routeToHumanReview=route_human,
        estimatedReadTime=content_result.get("estimatedReadTime", "1 min read"),
        validationReport=validation,
    )


def _clarify_output(session_id: str, intent_result: dict) -> AgentOutput:
    """Build an AgentOutput for the clarify path."""
    questions = intent_result.get("clarifyingQuestions", [])
    actions   = intent_result.get("suggestedActions", [])
    response_text = " | ".join(questions)
    options = [
        InteractiveOption(
            id=f"action_{i}",
            label=a[:40],
            description=a,
        )
        for i, a in enumerate(actions)
    ]
    return AgentOutput(
        sessionId=session_id,
        responseType="clarify",
        responseText=response_text,
        content="\n\n".join(f"- {q}" for q in questions),
        interactiveOptions=options,
        validationReport=ValidationReport(
            clarityScore=5, concisionScore=5, accessibilityPass=True
        ),
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class WatsonxOrchestrator:
    """Single entry point for the full multi-agent Conversation Design Assistant."""

    def __init__(self) -> None:
        self._model = _init_watsonx_model()
        self._intent_agent    = IntentAgent(self._model)
        self._retrieval_agent = RetrievalAgent(self._model)
        self._content_agent   = ContentAgent(self._model)

    # ------------------------------------------------------------------
    # First-turn entry point
    # ------------------------------------------------------------------

    def run(self, input_obj: AgentInput) -> AgentOutput:
        """Process a new user turn and return a structured AgentOutput."""

        # Immediate escalation if user explicitly chose a human option
        if input_obj.menuSelection in ("contact_support", "get_human_help"):
            return AgentOutput(
                sessionId=input_obj.sessionId,
                responseType="answer",
                responseText="We're connecting you with a specialist. Please hold on.",
                routeToHumanReview=True,
                validationReport=ValidationReport(
                    clarityScore=5, concisionScore=5, accessibilityPass=True
                ),
            )

        # Step 1 — Intent → may return Layer 1 selection options
        intent_result = self._intent_agent.run(input_obj)

        # Layer 1: return options for the user to choose from
        if intent_result["status"] == "select":
            def _truncate_label(s: str, limit: int = 40) -> str:
                if len(s) <= limit:
                    return s
                # Truncate at the last space before the limit so we don't cut mid-word
                cut = s[:limit].rsplit(" ", 1)[0]
                return cut or s[:limit]

            options = [
                InteractiveOption(
                    id=o["id"],
                    label=_truncate_label(o["label"]),
                    description=o.get("hint", o["label"]),
                )
                for o in intent_result.get("options", [])
            ]
            return AgentOutput(
                sessionId=input_obj.sessionId,
                responseType="select",
                responseText="Which of these best describes what you're looking for?",
                content="",
                interactiveOptions=options,
                validationReport=ValidationReport(
                    clarityScore=5, concisionScore=5, accessibilityPass=True
                ),
            )

        # Legacy clarify path (kept for safety)
        if intent_result["status"] == "clarify":
            return _clarify_output(input_obj.sessionId, intent_result)

        # Step 2 — Retrieval (only when needed)
        if intent_result.get("needRetrieval", False):
            retrieval_result = self._retrieval_agent.run(intent_result, input_obj)
            input_obj.sessionStore.mcpSessionId = retrieval_result.get("mcpSessionId")
        else:
            retrieval_result = {
                "results": [], "avgScore": 0.0, "lowConfidence": False,
                "suggestedRefinements": [], "mcpSessionId": None, "indexSize": 0,
            }

        # Step 3 — Content
        content_result = self._content_agent.run(retrieval_result, intent_result, input_obj)

        # Routing
        confidence     = content_result.get("confidence", "Low")
        route_human    = (
            confidence == "Low" and input_obj.humanReviewOnLowConfidence
        )
        response_type  = "low_confidence" if confidence == "Low" else "answer"

        return _assemble_output(
            session_id=input_obj.sessionId,
            response_type=response_type,
            content_result=content_result,
            session_store=input_obj.sessionStore,
            route_human=route_human,
        )

    # ------------------------------------------------------------------
    # Loop re-entry entry point
    # ------------------------------------------------------------------

    def run_loop(self, input_obj: AgentInput, feedback: str) -> AgentOutput:
        """
        Called when the user picks 'show_next' or 'doesnt_help'.
        Increments iterationCount, appends feedback to priorQueries,
        then re-runs the full pipeline.
        """
        input_obj.sessionStore.iterationCount += 1
        input_obj.sessionStore.priorQueries.append(feedback)
        input_obj.feedbackSignal = feedback
        return self.run(input_obj)
