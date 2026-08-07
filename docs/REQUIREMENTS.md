# Intently — Requirements

> **Version:** 1.0.0
> **Status:** Current
> **Last updated:** August 2025

---

## 1. Functional Requirements

### FR-01 · Query Submission

| ID | Requirement | Priority |
|---|---|---|
| FR-01.1 | The system SHALL accept a natural-language query of up to 500 characters via `POST /chat`. | Must |
| FR-01.2 | The system SHALL accept an optional `audience` parameter (`developer`, `admin`, `manager`, `beginner`, `intermediate`, `advanced`). Default: `developer`. | Should |
| FR-01.3 | The system SHALL accept an optional `maxLength` parameter (integer, characters). Default: 1500. | Should |
| FR-01.4 | The system SHALL assign a session ID to each conversation and maintain state across turns. | Must |

---

### FR-02 · Layer 1 — Intent Selection

| ID | Requirement | Priority |
|---|---|---|
| FR-02.1 | The system SHALL score the query against 7 intent patterns and return 3–5 selection options. | Must |
| FR-02.2 | Each option label SHALL be derived from the user's own query words and detected entities — not a generic category name. | Must |
| FR-02.3 | Each option SHALL carry a `queryFocus` string in the format `"intent — entity — full query"`. | Must |
| FR-02.4 | Each option label SHALL be 40 characters or fewer. | Must |
| FR-02.5 | Each option SHALL carry a `hint` string describing what the response will contain. | Should |
| FR-02.6 | The system SHALL apply smart brand casing to entity names (e.g. `oauth2` → `OAuth 2.0`, `node.js` → `Node.js`). | Should |
| FR-02.7 | If no intent pattern matches, the system SHALL return a general-howto option as the default. | Must |

---

### FR-03 · Layer 2 — Content Retrieval and Synthesis

| ID | Requirement | Priority |
|---|---|---|
| FR-03.1 | The system SHALL accept the selected option via `POST /select` and return a single structured content response. | Must |
| FR-03.2 | The system SHALL retrieve documentation exclusively from MS Learn MCP (`https://learn.microsoft.com/api/mcp`). | Must |
| FR-03.3 | The system SHALL deduplicate retrieved chunks by URL and text content before ranking. | Must |
| FR-03.4 | The system SHALL embed retrieved chunks using `ibm/slate-30m-english-rtrvr` (384-dimensional vectors). | Should |
| FR-03.5 | The system SHALL rank chunks using a per-session FAISS `IndexFlatIP` (cosine similarity). | Should |
| FR-03.6 | The system SHALL fall back to random unit-vector embeddings in mock mode or when the watsonx endpoint is unavailable. | Must |
| FR-03.7 | The content response SHALL include a plain-language insight block synthesised via watsonx Granite from the top-ranked chunk. | Should |
| FR-03.8 | The content response SHALL contain exactly one external reference: `[See more: Article Title](url)` pointing to the primary source document. | Must |
| FR-03.9 | The system SHALL NOT include speculative content, general training knowledge, or information not present in the retrieved source. | Must |

---

### FR-04 · Content Typing

| ID | Requirement | Priority |
|---|---|---|
| FR-04.1 | The system SHALL select one of five DITA-typed content formats based on detected intent: `steps`, `concept`, `code_snippet`, `troubleshoot`, `faq`. | Must |
| FR-04.2 | `steps` responses SHALL contain a numbered prerequisite list followed by a numbered step sequence. | Must |
| FR-04.3 | `code_snippet` responses SHALL contain a fenced code block with a language tag and inline annotations. | Must |
| FR-04.4 | `concept` responses SHALL contain a definition, how-it-works explanation, and a when-to-use section. | Should |
| FR-04.5 | `troubleshoot` responses SHALL contain symptom → cause → fix triples. | Should |
| FR-04.6 | `faq` responses SHALL contain Q&A pairs extracted from the retrieved content. | Should |

---

### FR-05 · Confidence and Validation

| ID | Requirement | Priority |
|---|---|---|
| FR-05.1 | Every response SHALL carry a `confidence` field: `High` (avgScore ≥ 0.75), `Medium` (≥ 0.50), `Low` (< 0.50). | Must |
| FR-05.2 | Low-confidence responses SHALL set `routeToHumanReview: true`. | Must |
| FR-05.3 | Every response SHALL carry a `validationReport` with `clarityScore` (0–5), `concisionScore` (0–5), and `accessibilityPass` (bool). | Must |
| FR-05.4 | `accessibilityPass` SHALL be `true` only when: no bare URLs in prose, at least one heading present, no passive voice in step text. | Should |
| FR-05.5 | Every response SHALL carry an `estimatedReadTime` string (e.g. `"2 min read"`). | Should |

---

### FR-06 · Session and Loop

| ID | Requirement | Priority |
|---|---|---|
| FR-06.1 | The system SHALL maintain per-session FAISS index state across loop iterations. | Must |
| FR-06.2 | On `feedbackSignal: "show_next"` or `"doesnt_help"`, the system SHALL re-enter the pipeline without re-presenting Layer 1. | Must |
| FR-06.3 | The session store SHALL persist: MCP session ID, iteration count, prior intents, prior queries, FAISS index bytes, FAISS chunk metadata. | Must |

---

### FR-07 · watsonx Orchestrate Integration

| ID | Requirement | Priority |
|---|---|---|
| FR-07.1 | The system SHALL expose a `POST /orchestrate/chat` endpoint that proxies to a deployed watsonx Orchestrate agent. | Should |
| FR-07.2 | The Orchestrate proxy SHALL normalise the Orchestrate response into the standard `AgentOutput` schema. | Should |
| FR-07.3 | The orchestrate embed server SHALL serve the Watson Orchestrate wxoLoader embed at `GET /`. | Should |
| FR-07.4 | The embed server SHALL expose `GET /config` to supply credentials to the UI without baking them into the HTML. | Should |
| FR-07.5 | The embed server SHALL expose `GET /api/token` to exchange the IAM API key for a bearer token, with a 5-minute pre-expiry cache. | Should |

---

### FR-08 · Mock Mode

| ID | Requirement | Priority |
|---|---|---|
| FR-08.1 | The system SHALL run fully in mock mode when `MOCK_MODE=true` — no credentials, no external API calls. | Must |
| FR-08.2 | Mock responses SHALL be structurally identical to live responses — same schema, same format types. | Must |
| FR-08.3 | Mock mode SHALL be the default when no `.env` file is present. | Must |

---

## 2. Non-Functional Requirements

### NFR-01 · Performance

| ID | Requirement | Target |
|---|---|---|
| NFR-01.1 | Layer 1 response time (intent scoring + entity extraction) | < 200 ms |
| NFR-01.2 | Layer 2 response time — mock mode | < 500 ms |
| NFR-01.3 | Layer 2 response time — live mode (MCP + watsonx) | < 5 s (p95) |
| NFR-01.4 | MCP search timeout | 15 s per call (httpx timeout) |

---

### NFR-02 · Reliability

| ID | Requirement |
|---|---|
| NFR-02.1 | The system SHALL fall back to mock embeddings if the watsonx embedding endpoint is unreachable. |
| NFR-02.2 | The system SHALL return a Low-confidence response rather than an error if MCP retrieval returns fewer than 2 chunks. |
| NFR-02.3 | The system SHALL retry MCP calls up to 3 times with exponential backoff on 429 or 5xx responses. |

---

### NFR-03 · Security

| ID | Requirement |
|---|---|
| NFR-03.1 | No credentials SHALL be committed to the repository. All secrets are loaded from environment variables at runtime. |
| NFR-03.2 | CORS SHALL be restricted to the production Code Engine URL and localhost origins. Wildcard `*` is not permitted in production. |
| NFR-03.3 | The system SHALL strip email addresses and phone numbers from query text before logging (PII pattern regex). |
| NFR-03.4 | IAM bearer tokens SHALL be cached with a 5-minute pre-expiry buffer and re-exchanged automatically. |
| NFR-03.5 | The `.env` file SHALL be listed in `.gitignore` and SHALL never be committed. |

---

### NFR-04 · Portability

| ID | Requirement |
|---|---|
| NFR-04.1 | The system SHALL run on Python 3.11+ on Windows, macOS, and Linux without code changes. |
| NFR-04.2 | The orchestrate embed server SHALL containerise to a Docker image < 500 MB. |
| NFR-04.3 | FAISS dependency SHALL be optional — the system SHALL run without it in mock mode using NumPy dot-product ranking. |

---

### NFR-05 · Observability

| ID | Requirement |
|---|---|
| NFR-05.1 | `GET /health` SHALL return mode flags (`mock_mode`, `watsonx_configured`, `orchestrate_configured`) for monitoring. |
| NFR-05.2 | Every response SHALL include `confidence`, `validationReport`, and `estimatedReadTime` for downstream quality tracking. |

---

## 3. Constraints

| Constraint | Detail |
|---|---|
| **Python version** | 3.11 or later |
| **No persistent database** | Sessions are in-memory per process. Redis is the upgrade path for multi-instance scale. |
| **MS Learn MCP only** | The PoC retrieval corpus is MS Learn. Other corpora require adding MCP endpoints or a custom retrieval adapter. |
| **Single region** | Code Engine deployment is eu-de (Frankfurt). Multi-region requires separate deployments behind a load balancer. |
| **Browser-only UI** | The Carbon UI is a single-page HTML file served by FastAPI. No mobile-native shell. |

---

## 4. Dependencies

### 4.1 Runtime (FastAPI server)

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ≥ 0.111.0 | REST API framework |
| `uvicorn[standard]` | ≥ 0.29.0 | ASGI server |
| `httpx` | ≥ 0.27.0 | Async HTTP client for MCP and watsonx |
| `pydantic` | ≥ 2.7.0 | Schema validation |
| `requests` | ≥ 2.32.0 | Synchronous HTTP (MCP session init) |
| `python-dotenv` | ≥ 1.0.0 | `.env` loader |
| `numpy` | ≥ 1.26.0 | Vector operations |

### 4.2 Optional (full mode)

| Package | Version | Purpose |
|---|---|---|
| `ibm-watsonx-ai` | ≥ 1.1.0 | Granite LLM + slate embedding |
| `faiss-cpu` | ≥ 1.8.0 | In-process vector similarity search |

### 4.3 Runtime (orchestrate embed server)

| Package | Version | Purpose |
|---|---|---|
| `Flask` | ≥ 3.0.0 | Web framework |
| `Flask-Cors` | ≥ 4.0.0 | CORS middleware |
| `gunicorn` | ≥ 22.0.0 | WSGI production server |
| `requests` | ≥ 2.32.0 | IAM token exchange |

### 4.4 External services

| Service | Auth | Purpose |
|---|---|---|
| MS Learn MCP (`https://learn.microsoft.com/api/mcp`) | None (public) | Documentation retrieval |
| watsonx.ai (`https://eu-de.ml.cloud.ibm.com`) | IAM API key | Granite LLM + slate embeddings |
| watsonx Orchestrate (`https://eu-de.watson-orchestrate.cloud.ibm.com`) | IAM API key | Orchestrate agent proxy |
| IBM Cloud IAM (`https://iam.cloud.ibm.com`) | API key | Bearer token exchange |

---

## 5. Acceptance Criteria

The system is considered production-ready when all of the following pass:

| Criterion | Test |
|---|---|
| AC-01 | `python launch.py` starts the server, opens the browser, and serves the UI at `http://localhost:8000` with `MOCK_MODE=true` and no credentials. | `test_runner.py` |
| AC-02 | `POST /chat` with any natural-language query returns a `responseType: "select"` response with 3–5 options within 200 ms. | `test_runner.py` Test A |
| AC-03 | `POST /select` with a valid option returns a `responseType: "answer"` response with `confidence`, `validationReport`, and `content`. | `test_runner.py` Test A |
| AC-04 | Low-signal queries (Test B) return `confidence: "Medium"` or lower and include `suggestedRefinements`. | `test_runner.py` Test B |
| AC-05 | Policy queries (Test C) return `routeToHumanReview: true` when confidence is Low. | `test_runner.py` Test C |
| AC-06 | The Code Engine production URL responds to `GET /health` with `{"status": "ok"}`. | Manual / CI |
| AC-07 | `validation/validate_outputs.py` passes with zero schema violations on all baseline test outputs. | `validate_outputs.py` |
