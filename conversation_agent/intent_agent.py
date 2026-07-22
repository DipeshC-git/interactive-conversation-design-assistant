"""
Intent & Clarification Agent (Agent 1)

Two-layer conversation architecture:

  Layer 1 — always runs on first user turn.
    Analyses the query, scores intents, extracts entities, then generates
    3–5 CONTEXTUAL selection options derived from the actual query content.
    These are NOT generic menus — they are specific angles on the user's
    own words, ready for the user to pick the one that matches their need.
    Returns: {"status": "select", "options": list[L1Option]}

  Layer 2 — runs after the user picks a Layer 1 option.
    The chosen option carries a sharpened queryFocus and chosenIntent.
    The orchestrator drives Retrieval → Content with that focus.
    Returns: {"status": "proceed", ...}

On loop re-entry (iteration > 0) it sharpens intent from session context
and always returns "proceed" — never re-presents Layer 1.
"""
from __future__ import annotations

import re

from conversation_agent.schemas import AgentInput

# ---------------------------------------------------------------------------
# Intent pattern registry
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

# Every intent drives retrieval — the retrieval agent decides what to fetch
RETRIEVAL_INTENTS = {
    "configure_oauth", "setup_auth", "policy_lookup",
    "code_request", "general_howto", "troubleshoot", "concept_explain",
}

ENTITY_ALLOWLIST = [
    "azure", "azure ad", "entra id", "node.js", "nodejs", "python", "javascript",
    "typescript", "oauth", "oauth2", "saml", "oidc", "openid", "active directory",
    "microsoft", "contoso", "device", "reset", "policy", "authentication",
    "authorization", "token", "api", "sdk", "rest", "graph api", "microsoft graph",
    "mfa", "multi-factor", "multifactor", "permissions", "consent", "scope",
    "msal", "adal", "pkce", "jwt", "access token", "refresh token", "id token",
    "401", "403", "500", "unauthorized", "forbidden",
]

# Human-readable labels for intent names used in option copy
_INTENT_LABEL: dict[str, str] = {
    "configure_oauth":  "Configure {entity}",
    "setup_auth":       "Set up {entity} authentication",
    "policy_lookup":    "Look up {entity} policy",
    "code_request":     "Get a {entity} code example",
    "general_howto":    "Step-by-step guide: {entity}",
    "concept_explain":  "What is {entity}?",
    "troubleshoot":     "Troubleshoot {entity} errors",
}

_INTENT_HINT: dict[str, str] = {
    "configure_oauth":  "Configuration steps, client credentials, redirect URIs",
    "setup_auth":       "Identity providers, protocols, SSO setup",
    "policy_lookup":    "Policy documents, compliance rules, procedures",
    "code_request":     "Working code snippet with annotations",
    "general_howto":    "Numbered steps, prerequisites, verification",
    "concept_explain":  "Plain-language definition, how it works, when to use it",
    "troubleshoot":     "Error diagnosis, likely causes, fixes",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_intents(user_input: str) -> list[dict]:
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
    for r in raw:
        r["score"] = round(r["hits"] / top_hits, 4)
    return raw


def _extract_entities(user_input: str) -> list[str]:
    text = user_input.lower()
    found = []
    for entity in ENTITY_ALLOWLIST:
        if entity in text and entity not in found:
            found.append(entity)
    quoted = re.findall(r'"([^"]+)"', user_input)
    found.extend(q for q in quoted if q.lower() not in found)
    return found


def _needs_retrieval(intent: str, user_input: str) -> bool:
    """Always retrieve for any recognised intent — retrieval is never skipped."""
    if intent in RETRIEVAL_INTENTS:
        return True
    # Fallback: any explicit documentation signal
    text = user_input.lower()
    return any(sig in text for sig in ["docs", "documentation", "reference", "article"])


# Entities that name a protocol/technology — preferred in labels
_PROTOCOL_ENTITIES = {
    "oauth", "oauth2", "saml", "oidc", "openid", "msal", "adal", "pkce",
    "jwt", "sso", "mfa", "multi-factor", "multifactor",
}

# Generic concept words that are not useful as a platform qualifier
_GENERIC_CONCEPTS = {
    "authentication", "authorization", "token", "api", "permissions",
    "consent", "scope", "device", "reset", "policy",
}

# Specific platform / runtime names that make a good "for <platform>" qualifier
_PLATFORM_ENTITIES = {
    "azure", "azure ad", "entra id", "node.js", "nodejs", "python",
    "javascript", "typescript", "microsoft", "microsoft graph", "graph api",
    "msal", "adal", "active directory", "contoso",
    "401", "403", "500", "unauthorized", "forbidden",
}


def _specificity(e: str) -> tuple[int, int]:
    """Score entity specificity: multi-word > single-word; longer > shorter."""
    return (e.count(" "), len(e))


def _entity_label(entities: list[str]) -> str:
    """
    Build a concise entity phrase for option copy.
    Priority: protocol > specific platform > fallback to longest non-generic.
    Only combine "proto for platform" when the platform is a real technology name.
    Multi-word entities score higher than single-word (more specific).
    """
    if not entities:
        return "this topic"

    protocols  = [e for e in entities if e in _PROTOCOL_ENTITIES]
    platforms  = [e for e in entities if e in _PLATFORM_ENTITIES]

    if protocols and platforms:
        proto = max(protocols, key=_specificity)
        plat  = max(platforms, key=_specificity)
        return f"{proto} for {plat}"
    if protocols:
        return max(protocols, key=_specificity)
    if platforms:
        return max(platforms, key=_specificity)
    # Exclude generic concept words; if only generics, return fallback
    specific = [e for e in entities if e not in _GENERIC_CONCEPTS]
    if not specific:
        return "this topic"
    return max(specific, key=_specificity)


# Known display names that need specific casing
_BRAND_CASE: dict[str, str] = {
    "oauth": "OAuth", "oauth2": "OAuth 2.0", "saml": "SAML", "oidc": "OIDC",
    "openid": "OpenID", "msal": "MSAL", "adal": "ADAL", "pkce": "PKCE",
    "jwt": "JWT", "sso": "SSO", "mfa": "MFA", "api": "API", "sdk": "SDK",
    "node.js": "Node.js", "nodejs": "Node.js", "python": "Python",
    "javascript": "JavaScript", "typescript": "TypeScript",
    "azure": "Azure", "azure ad": "Azure AD", "entra id": "Entra ID",
    "active directory": "Active Directory",
    "microsoft": "Microsoft", "microsoft graph": "Microsoft Graph",
    "graph api": "Graph API", "rest": "REST",
    "multi-factor": "multi-factor", "multifactor": "multi-factor",
    "401": "401 Unauthorized", "403": "403 Forbidden", "500": "500 errors",
    "unauthorized": "401 Unauthorized", "forbidden": "403 Forbidden",
}
_CONNECTORS = {"for", "of", "in", "on", "the", "a", "an", "and", "or", "with", "to"}


def _smart_case(phrase: str) -> str:
    """Apply known brand casing; keep connectors lowercase; title-case unknowns."""
    lower = phrase.lower()
    # Check whole-phrase first (handles "azure ad", "entra id", etc.)
    if lower in _BRAND_CASE:
        return _BRAND_CASE[lower]
    words = phrase.split(" ")
    result = []
    i = 0
    while i < len(words):
        # Try two-word match first (e.g. "azure ad")
        if i + 1 < len(words):
            two = f"{words[i]} {words[i+1]}".lower()
            if two in _BRAND_CASE:
                result.append(_BRAND_CASE[two])
                i += 2
                continue
        key = words[i].lower()
        if key in _BRAND_CASE:
            result.append(_BRAND_CASE[key])
        elif key in _CONNECTORS and i > 0:
            result.append(key)          # keep lowercase
        else:
            result.append(words[i].capitalize())
        i += 1
    return " ".join(result)


def _build_l1_options(
    intents: list[dict],
    entities: list[str],
    user_input: str,
) -> list[dict]:
    """
    Generate Layer 1 selection options from the scored intents and entities.

    Rules:
    - Always produce 3–5 options.
    - Each option is specific to the user's query — uses their own words and
      the detected entities, not generic category names.
    - The top-scored intent is always first.
    - If fewer than 3 intents scored, pad with the most useful adjacent intents
      for the detected entities.
    - Each option carries: id, label, hint, intent, queryFocus, needRetrieval.
    """
    entity = _entity_label(entities)
    top_names = [i["name"] for i in intents]

    # Pad to at least 3 candidates with sensible defaults
    defaults = ["general_howto", "concept_explain", "code_request",
                "troubleshoot", "configure_oauth"]
    for d in defaults:
        if d not in top_names:
            top_names.append(d)

    options: list[dict] = []
    seen: set[str] = set()

    for name in top_names[:5]:
        if name in seen:
            continue
        seen.add(name)
        label_tpl = _INTENT_LABEL.get(name, "Find information about {entity}")
        # Smart-case the entity unless it's the fallback placeholder
        entity_display = entity if entity == "this topic" else _smart_case(entity)
        raw_label = label_tpl.replace("{entity}", entity_display)
        label = raw_label[0].upper() + raw_label[1:]
        hint  = _INTENT_HINT.get(name, "")
        # queryFocus carries: intent — entity phrase — full original query
        # The retrieval agent uses this as the primary MCP search string
        query_focus = f"{name} — {entity} — {user_input}"
        options.append({
            "id":            name,
            "label":         label,
            "hint":          hint,
            "intent":        name,
            "queryFocus":    query_focus,
            "needRetrieval": _needs_retrieval(name, user_input),
        })

    return options[:5]


def _sharpen_intent(intent_result: dict, input_obj: AgentInput) -> str:
    base     = intent_result.get("chosenIntent", "")
    entities = intent_result.get("entities", [])
    prior    = input_obj.sessionStore.priorQueries
    prior_hint  = f" — refining from: {prior[-1]}" if prior else ""
    entity_hint = f" [{', '.join(entities[:3])}]" if entities else ""
    return f"{base}{entity_hint}{prior_hint}"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class IntentAgent:
    """Agent 1 — Two-layer intent disambiguation and content routing."""

    def __init__(self, model: object = None) -> None:
        self._model = model

    def run(self, input_obj: AgentInput) -> dict:
        """
        Layer 1 (iteration == 0, inputType != 'menu'):
          Returns {"status": "select", "options": list[dict], "entities": list[str]}
          The UI presents options; the user picks one.

        Layer 2 (inputType == 'menu' with menuSelection, or iteration > 0):
          Returns {"status": "proceed", "chosenIntent": str, "intentScore": float,
                   "entities": list[str], "needRetrieval": bool, "queryFocus": str}
          The orchestrator drives Retrieval → Content.
        """
        iteration = input_obj.sessionStore.iterationCount

        # ── Layer 2a: user picked a Layer 1 option ──────────────────────────
        if input_obj.inputType == "menu" and input_obj.menuSelection:
            intent_name  = input_obj.menuSelection
            entities     = _extract_entities(input_obj.userInput)
            query_focus  = input_obj.sessionStore.userPreferences.get(
                "selectedQueryFocus",
                f"{intent_name} [{', '.join(entities)}]",
            )
            input_obj.sessionStore.priorIntents.append(intent_name)
            return {
                "status":        "proceed",
                "chosenIntent":  intent_name,
                "intentScore":   1.0,
                "entities":      entities,
                "needRetrieval": _needs_retrieval(intent_name, input_obj.userInput),
                "queryFocus":    query_focus,
            }

        # ── Layer 2b: loop re-entry (show_next / doesnt_help) ───────────────
        if iteration > 0:
            intents  = _score_intents(input_obj.userInput)
            entities = _extract_entities(input_obj.userInput)
            top      = intents[0] if intents else {"name": "general_howto", "score": 0.5, "hits": 1}
            sharpened = _sharpen_intent(
                {"chosenIntent": top["name"], "entities": entities}, input_obj
            )
            input_obj.sessionStore.priorIntents.append(top["name"])
            return {
                "status":        "proceed",
                "chosenIntent":  top["name"],
                "intentScore":   top["score"],
                "entities":      entities,
                "needRetrieval": _needs_retrieval(top["name"], input_obj.userInput),
                "queryFocus":    sharpened,
            }

        # ── Layer 1: first turn — always return selection options ────────────
        intents  = _score_intents(input_obj.userInput)
        entities = _extract_entities(input_obj.userInput)
        options  = _build_l1_options(intents, entities, input_obj.userInput)
        return {
            "status":   "select",
            "options":  options,
            "entities": entities,
        }
