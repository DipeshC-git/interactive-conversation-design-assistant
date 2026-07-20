"""
Intent & Clarification Agent (Agent 1)

Rule-based intent scoring and entity extraction. On first entry it scores
the user input against known intent patterns and decides whether to
proceed or return clarifying questions. On loop re-entry it sharpens the
query focus using prior session context — never asks clarifying questions
during a loop iteration.
"""
from __future__ import annotations

import re

from conversation_agent.schemas import AgentInput

# ---------------------------------------------------------------------------
# Intent pattern registry
# Each key is an intent name; value is a list of keyword signals.
# Score = (matched keywords) / (total keywords), normalised 0.0–1.0.
# ---------------------------------------------------------------------------
INTENT_PATTERNS: dict[str, list[str]] = {
    "configure_oauth": [
        "oauth", "oauth2", "oauth 2", "openid", "oidc", "authorization code",
        "client credentials", "token endpoint", "azure ad", "entra id",
        "app registration", "client id", "client secret", "scope", "configure",
    ],
    "setup_auth": [
        "authentication", "auth", "sign in", "login", "sso", "saml",
        "set up", "setup", "enable", "integrate", "identity provider",
    ],
    "policy_lookup": [
        "policy", "policies", "compliance", "regulation", "rule",
        "device reset", "contoso", "guideline", "procedure", "requirement",
    ],
    "code_request": [
        "code", "snippet", "example", "sample", "node.js", "nodejs", "python",
        "javascript", "typescript", "implement", "library", "sdk", "package",
        "npm", "pip", "import",
    ],
    "general_howto": [
        "how", "how to", "how do i", "steps", "guide", "tutorial",
        "walkthrough", "configure", "install", "deploy", "set up",
    ],
    "concept_explain": [
        "what is", "explain", "definition", "overview", "understand",
        "difference between", "why", "when to use", "concept",
    ],
    "troubleshoot": [
        "error", "issue", "problem", "not working", "fail", "debug",
        "fix", "broken", "exception", "crash", "403", "401", "500",
    ],
}

# Intents that require retrieval from MS Learn MCP
RETRIEVAL_INTENTS = {
    "configure_oauth", "setup_auth", "policy_lookup",
    "code_request", "general_howto", "troubleshoot",
}

# Technology / product entity allowlist for extraction
ENTITY_ALLOWLIST = [
    "azure", "azure ad", "entra id", "node.js", "nodejs", "python", "javascript",
    "typescript", "oauth", "oauth2", "saml", "oidc", "openid", "active directory",
    "microsoft", "contoso", "device", "reset", "policy", "authentication",
    "authorization", "token", "api", "sdk", "rest", "graph api", "microsoft graph",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _score_intents(user_input: str) -> list[dict]:
    """
    Return intents sorted by score descending (0.0–1.0).

    Scoring strategy:
    - raw_hits = number of keywords matched
    - score = raw_hits / max_possible_hits across all intents (relative richness)
    - Intents with zero hits are excluded.
    - The returned score reflects how keyword-rich this intent is relative
      to the best-matching intent, preserving meaningful deltas.
    """
    text = user_input.lower()
    raw: list[dict] = []
    for intent, keywords in INTENT_PATTERNS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            raw.append({"name": intent, "score": hits, "hits": hits})

    if not raw:
        return []

    raw.sort(key=lambda x: x["score"], reverse=True)
    top_hits = raw[0]["hits"]

    # Normalise relative to top scorer so top = 1.0
    for r in raw:
        r["score"] = round(r["hits"] / top_hits, 4)

    return raw


def _extract_entities(user_input: str) -> list[str]:
    """Extract technology/product entities from the input."""
    text = user_input.lower()
    found = []
    for entity in ENTITY_ALLOWLIST:
        if entity in text and entity not in found:
            found.append(entity)
    # Also grab quoted strings as potential explicit references
    quoted = re.findall(r'"([^"]+)"', user_input)
    found.extend(q for q in quoted if q.lower() not in found)
    return found


def _needs_retrieval(intent: str, user_input: str) -> bool:
    """True when the intent or keywords suggest external doc lookup."""
    if intent in RETRIEVAL_INTENTS:
        return True
    text = user_input.lower()
    retrieval_signals = ["docs", "documentation", "reference", "article", "link", "page"]
    return any(sig in text for sig in retrieval_signals)


def _build_clarifying_questions(
    intents: list[dict],
    user_input: str,
) -> tuple[list[str], list[str]]:
    """
    Produce up to 2 short clarifying questions and 3 suggested quick actions.
    Called only on first entry when confidence is low.
    """
    questions: list[str] = []
    actions: list[str] = []

    top_names = [i["name"] for i in intents[:3]]

    if "setup_auth" in top_names and "configure_oauth" in top_names:
        questions.append(
            "Are you setting up a specific protocol? (e.g. OAuth 2.0, SAML, OIDC)"
        )
    if any(n in top_names for n in ("general_howto", "concept_explain")):
        questions.append(
            "Are you looking for step-by-step instructions or a conceptual overview?"
        )
    if not questions:
        questions.append(
            "Could you share more detail — which service or technology are you working with?"
        )
        questions.append(
            "Are you looking for documentation, a code example, or a policy reference?"
        )

    # Suggested quick actions ranked by relevance
    if "configure_oauth" in top_names:
        actions = [
            "Configure OAuth 2.0 for Azure AD",
            "Set up SAML-based single sign-on",
            "Explore Microsoft identity platform docs",
        ]
    elif "policy_lookup" in top_names:
        actions = [
            "Look up a specific policy document",
            "Browse compliance guidelines",
            "Contact your IT administrator",
        ]
    else:
        actions = [
            "Search Microsoft Learn documentation",
            "Find a step-by-step how-to guide",
            "Get a code example for my scenario",
        ]

    return questions[:2], actions[:3]


def _sharpen_intent(
    intent_result: dict,
    input_obj: AgentInput,
) -> str:
    """
    On loop re-entry: combine the existing chosenIntent with the most recent
    prior query and entities to produce a sharpened queryFocus string.
    """
    base = intent_result.get("chosenIntent", "")
    entities = intent_result.get("entities", [])
    prior = input_obj.sessionStore.priorQueries
    prior_hint = f" — refining from: {prior[-1]}" if prior else ""
    entity_hint = f" [{', '.join(entities[:3])}]" if entities else ""
    return f"{base}{entity_hint}{prior_hint}"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class IntentAgent:
    """Agent 1 — Intent detection and context-aware clarification."""

    def __init__(self, model: object = None) -> None:
        # model reserved for future watsonx LLM upgrade; unused in mock mode
        self._model = model

    def run(self, input_obj: AgentInput) -> dict:
        """
        Returns one of:
          {"status": "proceed", "chosenIntent": str, "intentScore": float,
           "entities": list[str], "needRetrieval": bool, "queryFocus": str}
          {"status": "clarify", "clarifyingQuestions": list[str],
           "suggestedActions": list[str]}
        """
        iteration = input_obj.sessionStore.iterationCount

        # --- menu shortcut ---
        if input_obj.inputType == "menu" and input_obj.menuSelection:
            intent_name = input_obj.menuSelection
            entities = _extract_entities(input_obj.userInput)
            result = {
                "status": "proceed",
                "chosenIntent": intent_name,
                "intentScore": 1.0,
                "entities": entities,
                "needRetrieval": _needs_retrieval(intent_name, input_obj.userInput),
                "queryFocus": f"{intent_name} [{', '.join(entities)}]",
            }
            input_obj.sessionStore.priorIntents.append(intent_name)
            return result

        intents = _score_intents(input_obj.userInput)
        entities = _extract_entities(input_obj.userInput)
        top = intents[0] if intents else {"name": "general_howto", "score": 0.5}

        # --- loop re-entry: sharpen, never clarify ---
        if iteration > 0:
            sharpened = _sharpen_intent(
                {"chosenIntent": top["name"], "entities": entities},
                input_obj,
            )
            input_obj.sessionStore.priorIntents.append(top["name"])
            return {
                "status": "proceed",
                "chosenIntent": top["name"],
                "intentScore": top["score"],
                "entities": entities,
                "needRetrieval": _needs_retrieval(top["name"], input_obj.userInput),
                "queryFocus": sharpened,
            }

        # --- first entry: check confidence ---
        # Clarify when:
        #   (a) two intents are tied (delta == 0), OR
        #   (b) top intent has few hits (≤ 2) AND a close competitor (delta < 0.25)
        second_score = intents[1]["score"] if len(intents) > 1 else 0.0
        delta = round(top["score"] - second_score, 4)
        top_hits = top.get("hits", 1)
        ambiguous = (delta == 0.0) or (delta < 0.25 and top_hits <= 2)
        if ambiguous:
            questions, actions = _build_clarifying_questions(intents, input_obj.userInput)
            return {
                "status": "clarify",
                "clarifyingQuestions": questions,
                "suggestedActions": actions,
            }

        query_focus = f"{top['name']} [{', '.join(entities[:3])}]"
        input_obj.sessionStore.priorIntents.append(top["name"])
        return {
            "status": "proceed",
            "chosenIntent": top["name"],
            "intentScore": top["score"],
            "entities": entities,
            "needRetrieval": _needs_retrieval(top["name"], input_obj.userInput),
            "queryFocus": query_focus,
        }
