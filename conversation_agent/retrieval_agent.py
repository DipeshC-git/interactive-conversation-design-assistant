"""
Information Retrieval Agent (Agent 2)

Calls the MS Learn MCP search_hybrid endpoint, embeds retrieved chunks
via watsonx embeddings, upserts into a per-session FAISS index, and
re-ranks all accumulated chunks on each loop iteration.

MOCK_MODE=true  → skips live MCP + watsonx calls, returns realistic mock data.
MOCK_MODE=false → calls live endpoints (requires WATSONX_BEARER_TOKEN + MCP).
"""
from __future__ import annotations

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


def _initialize_mcp_session() -> str:
    """POST to MCP initialize endpoint, return session ID."""
    resp = _backoff_request("POST", f"{MCP_BASE}/initialize",
                            json={"protocolVersion": "2024-11-05",
                                  "clientInfo": {"name": "ConvDesignAgent", "version": "1.0"}})
    session_id = resp.headers.get("Mcp-Session-Id", str(uuid.uuid4()))
    return session_id


def _call_search_hybrid(query: str, session_id: str, strictness: int) -> list[dict]:
    """Call MCP search_hybrid tool and return raw hits."""
    payload = {
        "method": "tools/call",
        "params": {
            "name": "search_hybrid",
            "arguments": {"query": query, "top_n": 5, "strictness": strictness},
        },
    }
    resp = _backoff_request("POST", MCP_BASE,
                            json=payload,
                            headers={"Mcp-Session-Id": session_id,
                                     "Content-Type": "application/json"})
    data = resp.json()
    return data.get("result", {}).get("content", [])


def _map_results(raw_hits: list[dict]) -> list[dict]:
    """Normalise raw MCP hits to internal schema."""
    mapped = []
    for h in raw_hits:
        mapped.append({
            "chunk_id": h.get("chunk_id", str(uuid.uuid4())),
            "file_path": h.get("file_path", h.get("url", "")),
            "page_numbers": str(h.get("page_numbers", "")),
            "text": h.get("text", h.get("content", "")),
            "snippet": h.get("snippet", "")[:200],
            "score": float(h.get("score", 0.5)),
            "images": h.get("images", []),
            "links": h.get("links", []),
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
    """Call watsonx embeddings API (used when MOCK_MODE=false)."""
    bearer = os.environ.get("WATSONX_BEARER_TOKEN", "")
    url = os.environ.get("WATSONX_URL", "").rstrip("/")
    resp = requests.post(
        f"{url}/v1/embeddings",
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        json={"model_id": "ibm/slate-30m-english-rtrvr", "inputs": texts},
        timeout=20,
    )
    resp.raise_for_status()
    vecs = [r["embedding"] for r in resp.json()["results"]]
    arr = np.array(vecs, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
    return arr / norms


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


def _build_query(intent_result: dict, input_obj: AgentInput) -> str:
    focus = intent_result.get("queryFocus", input_obj.userInput)
    entities = intent_result.get("entities", [])
    aud = input_obj.audience
    prior = input_obj.sessionStore.priorQueries
    base = f"{focus} for {aud}" if aud else focus
    if input_obj.sessionStore.iterationCount > 0 and prior:
        base = f"{base} — alternative approach to: {prior[-1]}"
    return _PII_PATTERN.sub("[REDACTED]", base)


def _suggest_refinements(query: str, intent: str) -> list[str]:
    narrower = f"{query} step-by-step tutorial with code example"
    broader = " ".join(query.split()[:4]) + " overview"
    return [narrower, broader]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class RetrievalAgent:
    """Agent 2 — RAG retrieval via MS Learn MCP + watsonx FAISS re-ranking."""

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
        iteration = session_store.iterationCount
        strictness = 3 if iteration % 2 == 1 else 2

        # --- MCP session ---
        if not session_store.mcpSessionId:
            session_store.mcpSessionId = (
                f"mock-session-{uuid.uuid4().hex[:8]}" if MOCK_MODE
                else _initialize_mcp_session()
            )

        # --- Retrieve ---
        query = _build_query(intent_result, input_obj)
        if MOCK_MODE:
            raw_chunks = _mock_chunks(intent_result.get("chosenIntent", "default"), iteration)
        else:
            raw_hits = _call_search_hybrid(query, session_store.mcpSessionId, strictness)
            raw_chunks = _map_results(raw_hits)

        if not raw_chunks:
            return {
                "results": [], "avgScore": 0.0, "lowConfidence": True,
                "suggestedRefinements": _suggest_refinements(query, intent_result.get("chosenIntent", "")),
                "mcpSessionId": session_store.mcpSessionId, "indexSize": 0,
            }

        # --- Embed + upsert FAISS ---
        texts = [c["text"] for c in raw_chunks]
        embeddings = _embed(texts)
        _upsert_faiss(embeddings, raw_chunks, session_store)

        # --- Re-rank from full session index ---
        reranked = _rerank(query, session_store, top_k=5)
        if not reranked:
            reranked = raw_chunks

        if MOCK_MODE:
            # FAISS scores on random unit vectors are near-zero — not meaningful.
            # Restore the pre-set realistic MCP scores keyed by chunk_id,
            # while keeping the FAISS-determined ordering.
            chunk_scores = {c["chunk_id"]: c["score"] for c in raw_chunks}
            for r in reranked:
                r["score"] = chunk_scores.get(r["chunk_id"], r["score"])
        else:
            # Normalise live FAISS inner-product scores to 0–1 range
            max_s = max(r["score"] for r in reranked) or 1.0
            for r in reranked:
                r["score"] = round(r["score"] / max_s, 4)

        avg_score = round(sum(r["score"] for r in reranked) / len(reranked), 4)

        low_confidence = avg_score < 0.45

        return {
            "results": reranked,
            "avgScore": avg_score,
            "lowConfidence": low_confidence,
            "suggestedRefinements": _suggest_refinements(query, intent_result.get("chosenIntent", "")),
            "mcpSessionId": session_store.mcpSessionId,
            "indexSize": len(session_store.faissChunks),
        }
