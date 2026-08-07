# Intently — Technical Specification

> **Version:** 1.0.0
> **Status:** Current
> **Last updated:** August 2025

---

## 1. System Overview

Intently is a two-layer, three-agent AI system for precision documentation retrieval. It turns a natural-language query into a single structured, source-grounded answer in two interactions, with no search reformulation required.

**Production URL:** https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud
**Local dev URL:** http://localhost:8000

---

## 2. System Architecture

### 2.1 Component Map

```
┌───────────────────────────────────────────────────────────────┐
│  Carbon UI  (ui/index.html — self-contained, served by FastAPI)│
│  Layer 1: intent tile selection  │  Layer 2: content card      │
└──────────────────────┬────────────────────────────────────────┘
                       │  HTTP (JSON)
┌──────────────────────▼────────────────────────────────────────┐
│  FastAPI Server  (conversation_agent/api_server.py)            │
│  POST /chat   POST /select   POST /orchestrate/chat   GET /health │
└──────────────────────┬────────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────────┐
│  WatsonxOrchestrator  (conversation_agent/orchestrator.py)     │
│  Session state · pipeline sequencing · FAISS store            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Agent 1 — IntentAgent  (intent_agent.py)                │  │
│  │ Agent 2 — RetrievalAgent  (retrieval_agent.py)          │  │
│  │ Agent 3 — ContentAgent  (content_agent.py)              │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────┬────────────────────────────────────────┘
                       │  HTTP (MCP JSON-RPC)
┌──────────────────────▼────────────────────────────────────────┐
│  MS Learn MCP  (https://learn.microsoft.com/api/mcp)           │
│  microsoft_docs_search  ·  microsoft_code_sample_search        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│  Orchestrate Embed Server  (orchestrate/app.py)                │
│  Flask · gunicorn · IBM Code Engine                            │
│  GET /  GET /config  GET /api/token  GET /health               │
│  Serves ui.html → loads watsonx Orchestrate wxoLoader embed    │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
User query
  │
  ▼ POST /chat  {sessionId, userInput}
IntentAgent.run()
  · _score_intents()      → 7-pattern keyword scorer (relative normalisation)
  · _extract_entities()   → entity allowlist matcher + quoted-string extractor
  · _build_l1_options()   → 3–5 queryFocus-carrying option dicts
  │
  ▼ Response {responseType:"select", interactiveOptions:[...]}
  │   UI renders tiles; user selects one
  │
  ▼ POST /select  {sessionId, selectedOption}
RetrievalAgent.run()
  · _build_primary_query()   → queryFocus → MCP search string
  · _call_search_docs()      → microsoft_docs_search (primary)
  · _call_search_code()      → microsoft_code_sample_search (code intents)
  · _build_entity_query()    → entity-only precision query (secondary call)
  · _dedup_chunks()          → URL + text-hash deduplication
  · _embed()                 → slate-30m-english-rtrvr (mock fallback: random unit vectors)
  · _upsert_faiss()          → IndexFlatIP upsert + normalise
  · _rerank()                → top-k cosine similarity against query embedding
  │
ContentAgent.run()
  · _select_format()         → TASK / CONCEPT / REFERENCE / troubleshoot / faq
  · _determine_confidence()  → avgScore → High / Medium / Low
  · _synthesize_content()    → build structured markdown from ranked chunks
  · _call_watsonx_summary()  → Granite insight block (mock fallback: extractive)
  · _run_validation()        → clarityScore · concisionScore · accessibilityPass
  │
  ▼ Response {responseType:"answer", content:"...", confidence:"...", validationReport:{...}}
```

---

## 3. Agent Specifications

### 3.1 Agent 1 — IntentAgent

**File:** `conversation_agent/intent_agent.py`

**Intent patterns (7):**

| Intent | Key signals |
|---|---|
| `configure_oauth` | oauth, openid, oidc, client credentials, app registration, entra id |
| `setup_auth` | authentication, sso, saml, identity provider, enable, integrate |
| `policy_lookup` | policy, compliance, regulation, rule, procedure |
| `code_request` | code, snippet, example, node.js, python, sdk, npm |
| `general_howto` | how, steps, guide, tutorial, deploy, install |
| `concept_explain` | what is, explain, definition, overview, difference between |
| `troubleshoot` | error, issue, 401, 403, 500, not working, debug |

**Scoring algorithm:**
- Keyword hit count per intent
- Relative normalisation: `score = hits / max_hits` (top intent always scores 1.0)
- Top 5 intents produce Layer 1 options; padded to minimum 3 from a default set

**Entity extraction:**
- Allowlist of 40+ technical terms (protocols, platforms, HTTP status codes)
- Quoted string extraction via regex `"([^"]+)"`
- `_entity_label()` priority: protocol entities > platform entities > non-generic

**queryFocus format:**
```
"{intent_name} — {entity_phrase} — {full_user_query}"
```
This string is the primary MCP search signal passed to Agent 2.

**Output schemas:**

Layer 1:
```json
{
  "status": "select",
  "options": [
    {
      "id": "configure_oauth",
      "label": "Configure OAuth 2.0 for Node.js",
      "hint": "Configuration steps, client credentials, redirect URIs",
      "intent": "configure_oauth",
      "queryFocus": "configure_oauth — oauth2 for node.js — How do I configure OAuth 2.0 for Node.js?",
      "needRetrieval": true
    }
  ],
  "entities": ["oauth2", "node.js"]
}
```

Layer 2 (after selection):
```json
{
  "status": "proceed",
  "chosenIntent": "configure_oauth",
  "intentScore": 1.0,
  "entities": ["oauth2", "node.js"],
  "needRetrieval": true,
  "queryFocus": "configure_oauth — oauth2 for node.js — How do I configure OAuth 2.0 for Node.js?"
}
```

---

### 3.2 Agent 2 — RetrievalAgent

**File:** `conversation_agent/retrieval_agent.py`

**MCP endpoint:** `https://learn.microsoft.com/api/mcp`
**Methods used:** `microsoft/docs/search`, `microsoft/code/search`

**Query strategy:**

1. Primary query: `queryFocus` string (intent + entity + full query)
2. Entity precision query: entity names only — fills gaps when primary over-retrieves
3. Code intent supplement: `microsoft_code_sample_search` before docs search

**Embedding:**
- Model: `ibm/slate-30m-english-rtrvr` via watsonx.ai
- Dimension: 384
- Mock fallback: random unit vectors (shape: `[n, 384]`)
- Normalised before upsert → inner product = cosine similarity

**FAISS index:**
- Type: `IndexFlatIP` (exact inner product, no quantisation)
- Per-session, serialised to `SessionStore.faissIndexBytes`
- Chunks stored in `SessionStore.faissChunks` (parallel to index vectors)
- Deduplication: SHA-256 of `url + text[:200]`

**Output schema:**
```json
{
  "results": [
    {
      "text": "...",
      "url": "https://learn.microsoft.com/...",
      "title": "...",
      "score": 0.87,
      "language": "javascript"
    }
  ],
  "avgScore": 0.74,
  "lowConfidence": false,
  "suggestedRefinements": [],
  "mcpSessionId": "abc123",
  "indexSize": 12
}
```

---

### 3.3 Agent 3 — ContentAgent

**File:** `conversation_agent/content_agent.py`

**DITA content type selection:**

| Intent | Format |
|---|---|
| `configure_oauth`, `setup_auth`, `general_howto` | `steps` (TASK) |
| `concept_explain` | `concept` (CONCEPT) |
| `code_request` | `code_snippet` (REFERENCE) |
| `troubleshoot` | `troubleshoot` |
| `policy_lookup` | `faq` |

**Content builders:**

| Builder | Output |
|---|---|
| `_build_steps()` | Numbered prerequisite + step sequence from retrieved text |
| `_build_code_snippet()` | Fenced code block with language tag + line-by-line annotations |
| `_build_concept()` | Definition + how-it-works + when-to-use paragraphs |
| `_build_troubleshoot()` | Symptom → cause → fix triples |
| `_build_faq()` | Q&A pairs from retrieved text |
| `_build_summary()` | Fallback: structured summary paragraphs |

**Watsonx Granite synthesis:**
- Model: `ibm/granite-13b-instruct-v2` (configurable)
- Produces a 2–3 sentence plain-language insight block from the top chunk
- Prepended to the structured content body
- Mock fallback: extractive first-sentence summary

**Confidence thresholds:**

| avgScore | Confidence |
|---|---|
| ≥ 0.75 | High |
| ≥ 0.50 | Medium |
| < 0.50 | Low (triggers `routeToHumanReview: true`) |

**Validation report:**
- `clarityScore` (0–5): heading density × passive voice penalty
- `concisionScore` (0–5): word count vs. max_length ratio
- `accessibilityPass` (bool): no bare URLs + headings present

**Output schema:**
```json
{
  "responseText": "One-line summary",
  "format": "steps",
  "content": "## Prerequisites\n\n1. ...",
  "interactiveOptions": [],
  "sources": [{"file_path": "https://learn.microsoft.com/...", "score": 0.87}],
  "confidence": "High",
  "suggestedRefinements": [],
  "estimatedReadTime": "2 min read",
  "validationReport": {
    "clarityScore": 4,
    "concisionScore": 5,
    "accessibilityPass": true
  }
}
```

---

## 4. API Specification

**Base URLs:**
- Production: `https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud`
- Local: `http://localhost:8000`

### POST /chat

Submit a natural-language query. Returns Layer 1 intent selection options.

**Request:**
```json
{
  "sessionId": "string (UUID recommended)",
  "userInput": "string",
  "audience": "developer | admin | manager | beginner | intermediate | advanced",
  "maxLength": 1500
}
```

**Response:**
```json
{
  "sessionId": "string",
  "responseType": "select",
  "responseText": "",
  "interactiveOptions": [
    {
      "id": "string",
      "label": "string (≤ 40 chars)",
      "description": "string",
      "queryFocus": "string"
    }
  ]
}
```

---

### POST /select

Submit the user's selected option. Returns Layer 2 structured content.

**Request:**
```json
{
  "sessionId": "string",
  "selectedOptionId": "string",
  "selectedQueryFocus": "string"
}
```

**Response:**
```json
{
  "sessionId": "string",
  "responseType": "answer",
  "responseText": "string",
  "format": "steps | concept | code_snippet | troubleshoot | faq | summary",
  "content": "string (markdown)",
  "interactiveOptions": [],
  "sources": [{"file_path": "string", "score": 0.0}],
  "confidence": "High | Medium | Low",
  "estimatedReadTime": "string",
  "validationReport": {
    "clarityScore": 0,
    "concisionScore": 0,
    "accessibilityPass": false
  }
}
```

---

### GET /health

**Response:**
```json
{
  "status": "ok",
  "mock_mode": true,
  "watsonx_configured": false,
  "orchestrate_configured": false
}
```

---

## 5. Data Models

All models are defined in `conversation_agent/schemas.py` using Pydantic v2.

| Model | Purpose |
|---|---|
| `AgentInput` | Input to the orchestrator (carries session state) |
| `AgentOutput` | Final output returned to the caller |
| `SessionStore` | Per-session state: FAISS index, prior intents, MCP session ID |
| `InteractiveOption` | One Layer 1 tile: id, label, description, queryFocus |
| `Source` | One retrieved source: file_path, score |
| `ValidationReport` | Per-response quality metrics |

---

## 6. Deployment

### 6.1 Local

```bash
# Install
python -m pip install -e ".[full]"          # includes faiss-cpu, ibm-watsonx-ai

# Configure
cp conversation_agent/.env.example conversation_agent/.env
# Edit .env — set MOCK_MODE=true for zero-credential demo

# Start
python launch.py                            # opens browser automatically
```

### 6.2 IBM Code Engine (orchestrate embed server)

| Parameter | Value |
|---|---|
| Production URL | `https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud` |
| Region | eu-de (Frankfurt) |
| Runtime | Python 3.11-slim |
| Server | gunicorn, 2 workers, port 8080 |
| Image | `conversation_agent/orchestrate/Dockerfile` |

Required environment variables (set in Code Engine — never in image):

| Variable | Description |
|---|---|
| `HOST_URL` | Watson Orchestrate host, e.g. `https://eu-de.watson-orchestrate.cloud.ibm.com` |
| `ORCHESTRATION_ID` | From Orchestrate embed snippet |
| `ORCHESTRATE_AGENT_ID` | From Orchestrate Deploy panel |
| `AGENT_ENV_ID` | From Orchestrate embed snippet |
| `ORCHESTRATE_API_KEY` | IBM Cloud IAM API key |
| `APP_URL` | `https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud` |

### 6.3 CORS Policy

Allowed origins (enforced in both `api_server.py` and `orchestrate/app.py`):

- `https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud`
- `http://localhost:8000`
- `http://127.0.0.1:8000`
- `http://localhost:5001`
- `http://127.0.0.1:5001`
- Additional origins via `APP_EXTRA_ORIGINS` environment variable (comma-separated)

---

## 7. Security

| Concern | Mitigation |
|---|---|
| Credentials in image | All secrets injected at runtime via env vars; never baked into Docker image |
| CORS | Explicit origin allowlist; wildcard `*` removed in production |
| PII in queries | `_PII_PATTERN` regex strips email addresses and phone numbers before logging |
| Gitignore | `.env` and `.env.*` excluded from all commits |
| IAM token rotation | Bearer token cached with 5-minute pre-expiry refresh |
