"""
Pydantic v2 data models for Intently.
All inter-agent boundaries and the public Input/Output contract are defined here.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Session state — carried across loop iterations
# ---------------------------------------------------------------------------

class SessionStore(BaseModel):
    mcpSessionId: str | None = None
    iterationCount: int = 0
    priorIntents: list[str] = Field(default_factory=list)
    priorQueries: list[str] = Field(default_factory=list)
    userPreferences: dict[str, Any] = Field(default_factory=dict)
    # FAISS index stored as bytes (serialised) between iterations; None on first run
    faissIndexBytes: bytes | None = None
    # Parallel chunk metadata list aligned with the FAISS index
    faissChunks: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Input
# ---------------------------------------------------------------------------

class AgentInput(BaseModel):
    sessionId: str
    userInput: str
    inputType: str = "text"                       # "text" | "menu"
    menuSelection: str | None = None
    userFormatPreference: str | None = None       # steps|faq|code_snippet|summary|table|interactive_menu
    sessionStore: SessionStore = Field(default_factory=SessionStore)
    maxLength: int = 1500
    audience: str = "developer"                   # developer|admin|manager|beginner|intermediate|advanced
    accessibility: bool = True
    humanReviewOnLowConfidence: bool = True
    feedbackSignal: str | None = None             # "show_next" | "doesnt_help" — set on loop re-entry


# ---------------------------------------------------------------------------
# Nested Output models
# ---------------------------------------------------------------------------

class InteractiveOption(BaseModel):
    id: str
    label: str
    description: str
    queryFocus: str = ""   # full retrieval signal — set on Layer 1 options only

    @field_validator("label")
    @classmethod
    def label_max_40(cls, v: str) -> str:
        if len(v) > 40:
            raise ValueError(f"label must be ≤ 40 chars, got {len(v)}: '{v}'")
        return v


class Source(BaseModel):
    file_path: str
    page_numbers: str = ""
    score: float = 0.0


class ValidationReport(BaseModel):
    clarityScore: int = Field(ge=0, le=5)
    concisionScore: int = Field(ge=0, le=5)
    accessibilityPass: bool


# ---------------------------------------------------------------------------
# Agent Output — the final JSON returned to the caller
# ---------------------------------------------------------------------------

class AgentOutput(BaseModel):
    sessionId: str
    responseType: str                             # "answer" | "clarify" | "low_confidence"
    responseText: str
    format: str | None = None                     # steps|faq|code_snippet|summary|table|interactive_menu
    content: str = ""                             # markdown body
    interactiveOptions: list[InteractiveOption] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    confidence: str = "Low"                       # "High" | "Medium" | "Low"
    mcpSessionId: str | None = None
    suggestedRefinements: list[str] = Field(default_factory=list)
    routeToHumanReview: bool = False
    estimatedReadTime: str = "1 min read"
    validationReport: ValidationReport = Field(
        default_factory=lambda: ValidationReport(
            clarityScore=0, concisionScore=0, accessibilityPass=False
        )
    )


# ---------------------------------------------------------------------------
# Internal agent result dicts (typed for documentation; not enforced at runtime)
# ---------------------------------------------------------------------------

# IntentAgent.run() returns one of:
#   {"status": "proceed", "chosenIntent": str, "intentScore": float,
#    "entities": list[str], "needRetrieval": bool, "queryFocus": str}
#   {"status": "clarify", "clarifyingQuestions": list[str], "suggestedActions": list[str]}

# RetrievalAgent.run() returns:
#   {"results": list[dict], "avgScore": float, "lowConfidence": bool,
#    "suggestedRefinements": list[str], "mcpSessionId": str | None, "indexSize": int}

# ContentAgent.run() returns:
#   {"responseText": str, "format": str, "content": str,
#    "interactiveOptions": list[dict], "sources": list[dict],
#    "confidence": str, "suggestedRefinements": list[str],
#    "estimatedReadTime": str, "validationReport": dict}
