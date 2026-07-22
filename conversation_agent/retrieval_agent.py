"""
Information Retrieval Agent (Agent 2)

Calls the MS Learn MCP search_hybrid endpoint, embeds retrieved chunks
via watsonx embeddings, upserts into a per-session FAISS index, and
re-ranks all accumulated chunks on each loop iteration.

MOCK_MODE=true  → skips live MCP + watsonx calls, returns realistic mock data.
MOCK_MODE=false → calls live endpoints (requires WATSONX_BEARER_TOKEN + MCP).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import numpy as np
import requests

from conversation_agent.schemas import AgentInput, SessionStore

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
MCP_BASE = "https://learn.microsoft.com/api/mcp"
EMBEDDING_DIM = 384   # slate-30m output dim (mock dimension matches)

# ---------------------------------------------------------------------------
# Mock data — realistic MS Learn chunks per topic
# ---------------------------------------------------------------------------

_MOCK_CHUNKS: dict[str, list[dict]] = {
    "configure_oauth": [
        {
            "chunk_id": "auth-oauth-001",
            "file_path": "azure/active-directory/develop/v2-oauth2-auth-code-flow.md",
            "page_numbers": "1-3",
            "text": (
                "The OAuth 2.0 authorization code flow is used in apps that are installed "
                "on a device to gain access to protected resources. Using this flow, apps "
                "can securely obtain access tokens and refresh tokens. Register your app "
                "in the Azure portal, set the redirect URI, and request the required scopes."
            ),
            "snippet": "OAuth 2.0 authorization code flow for Azure AD app registration.",
            "score": 0.91,
            "images": ["https://learn.microsoft.com/media/diagrams/oauth-code-flow.png"],
            "links": ["https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow"],
        },
        {
            "chunk_id": "auth-oauth-002",
            "file_path": "azure/active-directory/develop/quickstart-v2-nodejs-webapp.md",
            "page_numbers": "1-2",
            "text": (
                "Use the MSAL Node library to add authentication to your Node.js web app. "
                "Install msal-node, configure the confidentialClientApplication with your "
                "clientId, clientSecret, and authority. Call acquireTokenByCode after the "
                "user completes the authorization redirect."
            ),
            "snippet": "MSAL Node quickstart for OAuth 2.0 in Node.js.",
            "score": 0.87,
            "images": [],
            "links": ["https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-v2-nodejs-webapp"],
        },
        {
            "chunk_id": "auth-oauth-003",
            "file_path": "azure/active-directory/develop/msal-node-migration.md",
            "page_numbers": "2",
            "text": (
                "MSAL Node supports confidential and public client flows. For server-side "
                "Node.js apps, use ConfidentialClientApplication. Store client secrets in "
                "environment variables — never hardcode secrets in source code."
            ),
            "snippet": "MSAL Node confidential client app setup.",
            "score": 0.78,
            "images": [],
            "links": [],
        },
    ],
    "setup_auth": [
        {
            "chunk_id": "auth-setup-001",
            "file_path": "azure/active-directory/develop/authentication-vs-authorization.md",
            "page_numbers": "1",
            "text": (
                "Authentication confirms who you are. Authorization determines what you can do. "
                "Microsoft identity platform supports OAuth 2.0, OpenID Connect, and SAML. "
                "Choose the protocol based on your app type: web apps, SPAs, mobile, or daemon."
            ),
            "snippet": "Authentication vs Authorization on Microsoft identity platform.",
            "score": 0.72,
            "images": [],
            "links": ["https://learn.microsoft.com/en-us/azure/active-directory/develop/authentication-vs-authorization"],
        },
    ],
    "policy_lookup": [
        {
            "chunk_id": "policy-device-001",
            "file_path": "intune/configuration/device-reset-policy.md",
            "page_numbers": "1-4",
            "text": (
                "The device reset policy in Microsoft Intune allows administrators to remotely "
                "wipe a device to its factory settings. This policy applies to enrolled devices "
                "managed via Intune. Administrators require the Device Configuration Manager role. "
                "The reset action is irreversible — all data on the device is erased."
            ),
            "snippet": "Intune device reset policy — remote wipe to factory settings.",
            "score": 0.43,   # below 0.45 → low confidence for Test C
            "images": [],
            "links": ["https://learn.microsoft.com/en-us/mem/intune/remote-actions/devices-wipe"],
        },
    ],
    "default": [
        {
            "chunk_id": "general-001",
            "file_path": "microsoft-365/general/getting-started.md",
            "page_numbers": "1",
            "text": "Microsoft Learn provides documentation, training, and certifications for all Microsoft products.",
            "snippet": "Microsoft Learn getting started.",
            "score": 0.38,
            "images": [],
            "links": [],
        },
    ],
}


def _mock_chunks(intent: str, iteration: int) -> list[dict]:
    """Return mock MCP hits for a given intent, varying slightly per iteration."""
    base = _MOCK_CHUNKS.get(intent, _MOCK_CHUNKS["default"])
    if iteration > 0:
        # On re-entry, nudge scores slightly higher to simulate refinement gain
        base = [{**c, "score": min(c["score"] + 0.04 * iteration, 0.99)} for c in base]
    return base


# ---------------------------------------------------------------------------
# MCP helpers (live mode)
# ---------------------------------------------------------------------------

def _backoff_request(method: str, url: str, **kwargs) -> requests.Response:
    """HTTP call with exponential backoff: 1s → 2s → 4s, max 3 retries."""
    for attempt in range(3):
        try:
            resp = requests.request(method, url, timeout=15, **kwargs)
            if resp.status_code < 500:
                return resp
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError(f"MCP request failed after 3 retries: {url}")


def _mcp_call(method: str, params: dict, session_id: str | None = None) -> dict:
    """
    Send one JSON-RPC call to the MCP endpoint and parse the SSE response.
    MS Learn MCP speaks Server-Sent Events — every response is streamed as
    'event: message\\ndata: {...}' lines.
    """
    headers: dict = {"Content-Type": "application/json"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    for attempt in range(3):
        try:
            resp = requests.post(MCP_BASE, json=payload, headers=headers,
                                 stream=True, timeout=20)
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    return json.loads(line[5:].strip())
            return {}
        except Exception:
            time.sleep(2 ** attempt)
    return {}


def _initialize_mcp_session() -> str:
    """Initialize MCP session and return Mcp-Session-Id."""
    resp = requests.post(
        MCP_BASE,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05",
                         "clientInfo": {"name": "ConvDesignAgent", "version": "1.0"}}},
        stream=True, timeout=15,
    )
    session_id = resp.headers.get("Mcp-Session-Id", str(uuid.uuid4()))
    # drain SSE stream
    for _ in resp.iter_lines():
        pass
    return session_id


def _call_search_docs(query: str, session_id: str) -> list[dict]:
    """
    Call the microsoft_docs_search MCP tool.
    Returns a list of normalised chunk dicts.
    """
    data = _mcp_call(
        method="tools/call",
        params={"name": "microsoft_docs_search", "arguments": {"query": query}},
        session_id=session_id,
    )
    # MCP returns content as a list of {type, text} items inside result.content
    raw_items = data.get("result", {}).get("content", [])
    return _map_mcp_content(raw_items, query)


def _call_search_code(query: str, session_id: str, language: str = "javascript") -> list[dict]:
    """
    Call microsoft_code_sample_search for code-heavy intents.
    """
    data = _mcp_call(
        method="tools/call",
        params={"name": "microsoft_code_sample_search",
                "arguments": {"query": query, "language": language}},
        session_id=session_id,
    )
    raw_items = data.get("result", {}).get("content", [])
    return _map_mcp_content(raw_items, query)


def _clean_mcp_text(raw: str) -> tuple[str, list[str], list[str]]:
    """
    Clean a single MCP text item.

    MCP sometimes returns a JSON envelope like:
      {"results":[{"description":"...","codeSnippet":"...","url":"..."}]}
    or a plain markdown string.

    Returns (clean_text, urls, images).
    """
    import re as _re
    import json as _json

    urls: list[str] = []
    images: list[str] = []
    code_blocks: list[str] = []

    # ── Try to parse as a JSON envelope first ────────────────────────────────
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            obj = _json.loads(stripped)
            parts: list[str] = []
            # Flatten all string values we care about
            items = obj.get("results", [obj]) if isinstance(obj, dict) else obj
            for item in (items if isinstance(items, list) else [items]):
                if not isinstance(item, dict):
                    continue
                for key in ("description", "summary", "text", "content"):
                    v = item.get(key, "")
                    if isinstance(v, str) and v.strip():
                        parts.append(v.strip())
                # Collect code snippets — store separately, will be prepended
                cs = item.get("codeSnippet", item.get("code", ""))
                if cs:
                    lang = item.get("language", "")
                    code_blocks.append(f"```{lang}\n{cs.strip()}\n```")
                # Collect URLs
                for key in ("url", "link", "href"):
                    u = item.get(key, "")
                    if isinstance(u, str) and u.startswith("http"):
                        urls.append(u)
            raw = "\n\n".join(parts)
        except Exception:
            pass  # not valid JSON — treat as markdown

    # ── Now treat as markdown ─────────────────────────────────────────────────
    # Extract URLs
    urls += _re.findall(r"https?://learn\.microsoft\.com/[^\s\)\"'<>]+", raw)
    # Extract image URLs
    images = _re.findall(r"https?://\S+\.(?:png|jpg|jpeg|gif|svg|webp)(?:\?\S*)?", raw, _re.I)
    # Remove duplicate URLs
    urls = list(dict.fromkeys(urls))

    # Prepend any extracted code blocks to the text so _build_code_snippet
    # can pick them up via _extract_code_blocks()
    if code_blocks:
        raw = "\n\n".join(code_blocks) + "\n\n" + raw

    return raw.strip(), urls, images


def _map_mcp_content(raw_items: list[dict], query: str) -> list[dict]:
    """
    Normalise MCP tool response items to internal chunk schema.
    Each item has {type: 'text', text: '<markdown or JSON content>'}.
    Score is synthetic (position-based) since MCP doesn't return scores.
    """
    mapped = []
    for i, item in enumerate(raw_items[:5]):
        raw_text = item.get("text", "")
        text, urls, images = _clean_mcp_text(raw_text)

        file_path = urls[0] if urls else f"microsoft-learn/result-{i+1}.md"
        # Synthetic score: first result scores highest
        score = round(0.95 - (i * 0.08), 2)

        mapped.append({
            "chunk_id": f"mcp-{uuid.uuid4().hex[:8]}",
            "file_path": file_path,
            "page_numbers": "",
            "text": text[:1200],   # slightly larger budget now text is clean
            "snippet": text[:250],
            "score": score,
            "images": images[:2],
            "links": urls[:2],
        })
    return mapped


# ---------------------------------------------------------------------------
# Embedding + FAISS helpers
# ---------------------------------------------------------------------------

def _mock_embed(texts: list[str]) -> np.ndarray:
    """
    Deterministic mock embedding: hash each text to a unit vector.
    Preserves cosine-similarity ordering within the same query batch.
    """
    vecs = []
    for text in texts:
        rng = np.random.default_rng(abs(hash(text[:64])) % (2 ** 32))
        v = rng.standard_normal(EMBEDDING_DIM).astype("float32")
        v /= np.linalg.norm(v) + 1e-9
        vecs.append(v)
    return np.array(vecs, dtype="float32")


def _live_embed(texts: list[str]) -> np.ndarray:
    """
    Call watsonx Embeddings client via ibm-watsonx-ai SDK.

    Credential resolution order (mirrors orchestrator.py):
      1. WATSONX_IAM_APIKEY (standard IBM Cloud IAM key — recommended)
      2. WATSONX_BEARER_TOKEN (Watson Orchestrate SSO token — legacy)

    Falls back to deterministic mock embeddings on any error.
    FAISS ordering remains valid; scores are restored from MCP position weights.
    """
    url  = os.environ.get("WATSONX_URL", "").rstrip("/")
    proj = os.environ.get("WATSONX_PROJECT_ID", "")
    if not (url and proj):
        return _mock_embed(texts)
    try:
        from ibm_watsonx_ai import Credentials           # type: ignore
        from ibm_watsonx_ai.foundation_models import Embeddings  # type: ignore

        iam_key = os.environ.get("WATSONX_IAM_APIKEY", "")
        bearer  = os.environ.get("WATSONX_BEARER_TOKEN", "")

        if iam_key:
            creds = Credentials(url=url, api_key=iam_key)
        elif bearer:
            creds = Credentials(url=url, token=bearer)
        else:
            return _mock_embed(texts)

        embed_client = Embeddings(
            model_id="ibm/slate-30m-english-rtrvr",
            credentials=creds,
            project_id=proj,
        )
        response = embed_client.embed_documents(texts=texts)
        # SDK returns list[list[float]]
        arr = np.array(response, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        return arr / norms
    except Exception:
        # Graceful fallback: deterministic mock embeddings
        return _mock_embed(texts)


def _embed(texts: list[str]) -> np.ndarray:
    return _mock_embed(texts) if MOCK_MODE else _live_embed(texts)


def _upsert_faiss(embeddings: np.ndarray, chunks: list[dict],
                  session_store: SessionStore) -> None:
    """Add embeddings to the per-session FAISS flat index."""
    import faiss  # type: ignore

    if session_store.faissIndexBytes:
        index = faiss.deserialize_index(
            np.frombuffer(session_store.faissIndexBytes, dtype="uint8")
        )
    else:
        index = faiss.IndexFlatIP(EMBEDDING_DIM)

    index.add(embeddings)
    session_store.faissIndexBytes = bytes(faiss.serialize_index(index))
    session_store.faissChunks.extend(chunks)


def _rerank(query: str, session_store: SessionStore, top_k: int = 5) -> list[dict]:
    """Embed query and search the FAISS index; return top_k chunks."""
    import faiss  # type: ignore

    if not session_store.faissIndexBytes or not session_store.faissChunks:
        return []

    index = faiss.deserialize_index(
        np.frombuffer(session_store.faissIndexBytes, dtype="uint8")
    )
    q_vec = _embed([query])
    distances, indices = index.search(q_vec, min(top_k, index.ntotal))

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        chunk = dict(session_store.faissChunks[idx])
        chunk["score"] = float(dist)
        results.append(chunk)
    return results


# ---------------------------------------------------------------------------
# Query building helpers
# ---------------------------------------------------------------------------

_PII_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"  # email
    r"|\b(\+?1?\s?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})\b"  # phone
)


def _build_primary_query(intent_result: dict, input_obj: AgentInput) -> str:
    """
    Build the primary MCP search query from the Layer 1 queryFocus.

    The queryFocus is set by the Intent Agent as:
      "<intent_name> — <entity_phrase> — <full_user_input>"

    We extract the original user query (the richest natural-language signal)
    and append the entity phrase for precision, then PII-redact.
    """
    query_focus = input_obj.sessionStore.userPreferences.get(
        "selectedQueryFocus",
        intent_result.get("queryFocus", input_obj.userInput),
    )
    # Extract the original user query from the queryFocus (part after 2nd " — ")
    parts = query_focus.split(" — ", 2)
    base = parts[2].strip() if len(parts) == 3 else input_obj.userInput.strip()

    # Append entity phrase if not already present in base
    entities = intent_result.get("entities", [])
    if entities:
        ent_str = " ".join(entities[:3])
        if ent_str.lower() not in base.lower():
            base = f"{base} {ent_str}"

    # On loop re-entry steer away from the prior result
    if input_obj.sessionStore.iterationCount > 0:
        base = f"{base} alternative approach"

    return _PII_PATTERN.sub("[REDACTED]", base.strip())


def _build_entity_query(intent_result: dict) -> str:
    """
    Precision query: intent keyword + detected entities.
    Used as a second MCP call to fill gaps the primary query may miss.
    """
    intent = intent_result.get("chosenIntent", "")
    entities = intent_result.get("entities", [])
    keyword_map = {
        "configure_oauth":  "configure OAuth 2.0",
        "setup_auth":       "set up authentication",
        "code_request":     "code example",
        "troubleshoot":     "troubleshoot error",
        "policy_lookup":    "policy",
        "concept_explain":  "what is",
        "general_howto":    "how to",
    }
    kw = keyword_map.get(intent, "")
    ent = " ".join(entities[:2]) if entities else ""
    return _PII_PATTERN.sub("[REDACTED]", f"{kw} {ent}".strip())


def _suggest_refinements(user_input: str, intent: str) -> list[str]:
    words = user_input.strip().rstrip("?").strip()
    narrower = f"{words} step-by-step with code example"
    short    = " ".join(words.split()[:5])
    broader  = f"{short} overview and concepts"
    return [narrower, broader]


def _dedup_chunks(chunks: list[dict]) -> list[dict]:
    """Remove duplicate chunks by chunk_id, preserving order."""
    seen: set[str] = set()
    out: list[dict] = []
    for c in chunks:
        cid = c.get("chunk_id", "")
        if cid and cid in seen:
            continue
        seen.add(cid)
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class RetrievalAgent:
    """
    Agent 2 — Information Retrieval Agent.

    Retrieves everything the Intent Agent found relevant from MS Learn MCP:
      1. Primary query  — derived from the full queryFocus selected in Layer 1
      2. Entity query   — precision search (intent keyword + entities)
      3. Code query     — for code_request / configure_oauth intents

    All results are deduplicated, embedded, FAISS-indexed, and re-ranked.
    The Content Agent receives the full ranked result set.
    """

    def __init__(self, model: object = None) -> None:
        self._model = model

    def run(self, intent_result: dict, input_obj: AgentInput) -> dict:
        """
        Returns:
          {"results": list[dict], "avgScore": float, "lowConfidence": bool,
           "suggestedRefinements": list[str], "mcpSessionId": str|None, "indexSize": int}
        """
        if not intent_result.get("needRetrieval", False):
            return {
                "results": [], "avgScore": 0.0, "lowConfidence": False,
                "suggestedRefinements": [], "mcpSessionId": None, "indexSize": 0,
            }

        session_store: SessionStore = input_obj.sessionStore
        iteration     = session_store.iterationCount
        intent        = intent_result.get("chosenIntent", "default")

        # MCP session init
        if not session_store.mcpSessionId:
            session_store.mcpSessionId = (
                f"mock-session-{uuid.uuid4().hex[:8]}" if MOCK_MODE
                else _initialize_mcp_session()
            )

        # Build queries
        primary_q = _build_primary_query(intent_result, input_obj)
        entity_q  = _build_entity_query(intent_result)

        if MOCK_MODE:
            raw_chunks = _mock_chunks(intent, iteration)
        else:
            raw_chunks: list[dict] = []

            # Code-heavy intents: code sample search first, then docs
            if intent in ("configure_oauth", "code_request"):
                entities = intent_result.get("entities", [])
                ent_str  = " ".join(entities).lower()
                lang = (
                    "python"     if "python"     in ent_str else
                    "typescript" if "typescript" in ent_str else
                    "javascript"
                )
                raw_chunks.extend(_call_search_code(primary_q, session_store.mcpSessionId, lang))

            # Primary docs search — always runs
            raw_chunks.extend(_call_search_docs(primary_q, session_store.mcpSessionId))

            # Entity precision search — runs when entity_q adds new signal
            if entity_q and entity_q != primary_q:
                raw_chunks.extend(_call_search_docs(entity_q, session_store.mcpSessionId))

            # Deduplicate before embedding
            raw_chunks = _dedup_chunks(raw_chunks)

        if not raw_chunks:
            return {
                "results": [], "avgScore": 0.0, "lowConfidence": True,
                "suggestedRefinements": _suggest_refinements(input_obj.userInput, intent),
                "mcpSessionId": session_store.mcpSessionId, "indexSize": 0,
            }

        # Embed + FAISS upsert
        texts      = [c["text"] for c in raw_chunks]
        embeddings = _embed(texts)
        _upsert_faiss(embeddings, raw_chunks, session_store)

        # Re-rank from full session index using the primary query
        reranked = _rerank(primary_q, session_store, top_k=5)
        if not reranked:
            reranked = raw_chunks

        # Restore MCP position-based scores for confidence calculation
        # (FAISS is used only for ordering; its raw scores are not calibrated)
        chunk_scores = {c["chunk_id"]: c["score"] for c in raw_chunks}
        for r in reranked:
            r["score"] = chunk_scores.get(r["chunk_id"], r["score"])

        avg_score      = round(sum(r["score"] for r in reranked) / len(reranked), 4)
        low_confidence = avg_score < 0.45

        return {
            "results": reranked,
            "avgScore": avg_score,
            "lowConfidence": low_confidence,
            "suggestedRefinements": _suggest_refinements(input_obj.userInput, intent),
            "mcpSessionId": session_store.mcpSessionId,
            "indexSize": len(session_store.faissChunks),
        }
