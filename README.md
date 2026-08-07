# Intently — Conversation Precision by Design

> **IBM AI Builders Challenge · August Wildcard Challenge**
> Built entirely with IBM Bob

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/api-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![MS Learn MCP](https://img.shields.io/badge/retrieval-MS%20Learn%20MCP-0078d4)](https://learn.microsoft.com/api/mcp)
[![watsonx Orchestrate](https://img.shields.io/badge/AI-watsonx%20Orchestrate-0f62fe)](https://www.ibm.com/products/watsonx-orchestrate)
[![IBM Bob](https://img.shields.io/badge/built%20with-IBM%20Bob-0f62fe)](http://ibm.biz/university-bob)

---

## Problem Statement

Most documentation systems assume that users know what to search for. In practice, they rarely do. Developers, administrators, and technical teams spend a significant portion of their time navigating search results, comparing sources, and filtering out outdated or irrelevant content — before they can act on any of it.

Standard search returns links. AI chatbots return answers that may be hallucinated. Neither addresses the root problem: **users cannot articulate precise intent before they have context, and they cannot get context without a precise query.**

The result is a loop of reformulation, noise, and wasted time that produces no artefacts and advances no work.

---

## Solution Description

**Intently** is a design exploration of what becomes possible when **precision, not retrieval, is treated as the primary goal.**

Instead of returning answers immediately, the system first surfaces a small set of context-specific options derived from a trusted documentation source — Microsoft Learn. The user selects the angle that matches their intent. The system responds with a single, structured, fully grounded answer. No noise. No hallucination by design.

The result is not faster search, but the **removal of search as a problem.** By combining intent recognition, context selection, and typed content representation, the system reduces ambiguity, eliminates irrelevant results, and prevents hallucinated responses at the architectural level.

The conversation is two layers:

1. **Layer 1 — Context Selection:** The system surfaces 3–5 distinct, contextually derived angles on the user's question as selectable tiles. Each tile is a specific angle grounded in the user's own words — not a generic category.
2. **Layer 2 — Typed Content:** The user selects the angle that matches their situation. The system retrieves, ranks, and synthesises a typed, structured, plain-language answer in under 3 seconds — directly usable output, not a list of links to evaluate.

The architectural pattern — intent recognition → context selection → typed content representation — is reusable across any documentation ecosystem: internal knowledge bases, compliance libraries, support portals, product manuals. Microsoft Learn is the demonstration corpus. The design is general-purpose.

---

## AI Approach and Architecture

### Three-Agent Pipeline

```
User Query
    â”‚
    â–¼
POST /chat â†’ Intent Agent â†’ Layer 1 options (responseType: "select")
    â”‚
    â–¼ User selects one option
POST /select â†’ Retrieval Agent â†’ Content Agent â†’ Layer 2 content (responseType: "answer")
    â”‚
    â–¼ "See more" link in content body
Opens primary MS Learn article in new tab
```

**Agent 1 — Intent & Context Agent**
- Scores 7 intent patterns (configure, setup, code, howto, concept, troubleshoot, policy) using keyword overlap with relative normalisation.
- Extracts named entities with protocol/platform/generic classification (OAuth, Azure AD, Node.js, etc.) and applies smart brand casing.
- Produces 3–5 contextual Layer 1 options — each a specific angle on the user's own words.
- Every option carries a `queryFocus` string: `"<intent> — <entity phrase> — <full user query>"` — passed directly to the Retrieval Agent as the primary MCP search signal.

**Agent 2 — Information Retrieval Agent**
- Builds the primary MCP query from the selected `queryFocus`, appending detected entities for precision.
- Runs a secondary entity precision query as a second MCP call to fill result gaps.
- For code-heavy intents, runs `microsoft_code_sample_search` first, then supplements with `microsoft_docs_search`.
- Deduplicates results, embeds via watsonx `slate-30m-english-rtrvr` (graceful mock fallback), upserts into a per-session FAISS `IndexFlatIP`, and re-ranks the full session index.

**Agent 3 — Content Representation Agent**
- Receives the full ranked retrieval result set.
- Selects the appropriate DITA content type (TASK / CONCEPT / REFERENCE) based on intent.
- Synthesises a plain-language insight block from the top chunk via watsonx Granite.
- Builds structured content: numbered steps, annotated code blocks with language detection, FAQ pairs, or summary paragraphs — all from real retrieved text.
- Appends a single `[See more: Article Title](url)` link — the only external reference. No hallucination.

**watsonx Orchestrate Integration**
- The full system prompt is deployed to watsonx Orchestrate with the MS Learn MCP server as a native tool.
- A `/orchestrate/chat` proxy endpoint in the FastAPI server forwards to the deployed Orchestrate agent and normalises the response into the same output schema.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                 Intently — Conversation Precision by Design      │
│                                                                  │
│  Carbon UI (ui/index.html)                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Layer 1 — Intent selection tiles (3–5 options)             │  │
│  │ Layer 2 — Structured content card + "See more" link        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                    FastAPI Server                                 │
│           POST /chat  POST /select  GET /health                  │
│                          │                                       │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │               WatsonxOrchestrator                         │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │ Agent 1 — Intent & Context Agent                    │  │   │
│  │  │  Score 7 intents · extract entities · build options  │  │   │
│  │  │  queryFocus: "intent — entity — full user query"     │  │   │
│  │  └────────────────────────┬────────────────────────────┘  │   │
│  │          status: select   │ status: proceed                │   │
│  │          (Layer 1)        ▼ (Layer 2)                      │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │ Agent 2 — Information Retrieval Agent               │  │   │
│  │  │  Primary query from queryFocus                      │  │   │
│  │  │  + Entity precision query                           │  │   │
│  │  │  + Code sample search (code intents)                │  │   │
│  │  │  Dedup · embed (slate-30m) · FAISS index · rerank   │  │   │
│  │  └────────────────────────┬────────────────────────────┘  │   │
│  │                           ▼                                │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │ Agent 3 — Content Representation Agent              │  │   │
│  │  │  (watsonx Orchestrate + MS Learn MCP)               │  │   │
│  │  │  DITA type: TASK / CONCEPT / REFERENCE              │  │   │
│  │  │  Insight block · structured body · "See more" link  │  │   │
│  │  │  interactiveOptions: []  (no options in Layer 2)    │  │   │
│  │  └─────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                    MS Learn MCP API
              https://learn.microsoft.com/api/mcp
              microsoft_docs_search
              microsoft_code_sample_search
```

**Stack:** Python 3.11 · FastAPI · uvicorn · Pydantic v2 · FAISS · NumPy · httpx · watsonx Orchestrate · MS Learn MCP · Carbon Design System

---

## Challenge Theme — August Wildcard

> *AI is evolving from a productivity tool into a true collaborator that can help people plan, coordinate, decide, and execute work more effectively. Build solutions that help individuals, teams, and organisations achieve better outcomes through intelligent automation, workflow orchestration, and decision support.*

This project addresses all three pillars directly:

| Challenge pillar | Intently |
|---|---|
| **Intelligent automation** | Documentation research is fully automated — intent scoring, multi-query retrieval, FAISS ranking, and content synthesis run without user effort. The user makes one decision: which angle. |
| **Workflow orchestration** | Three agents orchestrated in sequence by a session-aware controller. watsonx Orchestrate adds a second orchestration layer where MS Learn MCP is invoked natively as a tool. |
| **Decision support** | Every response carries a `confidence` rating (High / Medium / Low) and a `validationReport` (`clarityScore`, `concisionScore`, `accessibilityPass`). |

| Challenge example area | Intently |
|---|---|
| Workflow automation tools | Multi-query MCP retrieval + FAISS ranking automated end to end |
| AI co-workers | Three-agent pipeline acting as senior technical writer + researcher |
| Decision intelligence platforms | Confidence scoring and validation report on every response |
| Business process orchestration systems | watsonx Orchestrate with MS Learn MCP as native tool |

---

## Repository Structure

```
conversation_agent/
  __init__.py             package marker
  schemas.py              Pydantic v2 models: AgentInput, AgentOutput, SessionStore
  intent_agent.py         Agent 1: intent scoring, entity extraction, Layer 1 options
  retrieval_agent.py      Agent 2: multi-query MCP retrieval, FAISS RAG pipeline
  content_agent.py        Agent 3: content synthesis, validation, "See more" link
  orchestrator.py         WatsonxOrchestrator: session state, pipeline sequencing
  api_server.py           FastAPI server: /chat, /select, /orchestrate/chat, /health
  .env.example            documented environment template

  orchestrate/
    unified_instructions.md   Active system instructions deployed to Orchestrate
    system_instructions.md    Layer 2 content agent instructions (reference)
    agent.yaml                Orchestrate agent definition
    mslearn_mcp_tool.json     MS Learn MCP tool registration
    google_developer_mcp_tool.json  Google Developer MCP tool registration
    google-mcp-proxy/         Node.js MCP proxy for Google Developer APIs

ui/
  index.html              Carbon Design System enterprise UI (self-contained)

test_outputs/
  baseline_test_a.json    Baseline: specific how-to query
  baseline_test_b.json    Baseline: ambiguous clarification query
  baseline_test_c.json    Baseline: low-confidence policy lookup

validation/
  validate_outputs.py     Post-hoc schema and accessibility validator

launch.py               One-command startup (opens browser automatically)
run.ps1                 PowerShell startup script (Windows)
test_runner.py          Runs all test cases and saves outputs
pyproject.toml          Project metadata and dependencies
```

---

## Getting Started

### Quick Start (Mock Mode — no credentials needed)

```bash
git clone https://github.com/DipeshC-git/interactive-conversation-design-assistant.git
cd interactive-conversation-design-assistant

python -m pip install fastapi uvicorn httpx numpy pydantic requests python-dotenv

cp conversation_agent/.env.example conversation_agent/.env
# MOCK_MODE=true by default â€” no credentials needed

python launch.py
# Or: python -m uvicorn conversation_agent.api_server:app --port 8000
# Open http://localhost:8000
```

### Live Mode (MS Learn MCP + watsonx)

Set the following in `conversation_agent/.env`:

```env
MOCK_MODE=false

# Required for live watsonx generation (optional — falls back to mock)
WATSONX_IAM_APIKEY=your_iam_api_key
WATSONX_PROJECT_ID=your_project_id
WATSONX_URL=https://us-south.ml.cloud.ibm.com

# Required for watsonx Orchestrate proxy endpoint
ORCHESTRATE_INSTANCE_URL=your_orchestrate_url
ORCHESTRATE_API_KEY=your_orchestrate_api_key
ORCHESTRATE_AGENT_ID=your_agent_id
```

MS Learn MCP retrieval works with no API key — it is a public endpoint.

### Windows PowerShell

```powershell
.\run.ps1           # standard start
.\run.ps1 -Mock     # force mock mode
.\run.ps1 -Port 8080
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Submit a query → returns Layer 1 intent selection options |
| `POST` | `/select` | Submit selected option → returns Layer 2 structured content |
| `POST` | `/orchestrate/chat` | Proxy to deployed watsonx Orchestrate agent |
| `GET` | `/health` | Returns server status and mode flags |

### Example: POST /chat

```json
{
  "sessionId": "abc123",
  "userInput": "How do I configure OAuth 2.0 for Node.js?"
}
```

Response:
```json
{
  "responseType": "select",
  "interactiveOptions": [
    { "id": "opt_1", "label": "Configure OAuth 2.0 for Node.js", "queryFocus": "configure — OAuth 2.0 Node.js — How do I configure OAuth 2.0 for Node.js?" },
    ...
  ]
}
```

---

## Feasibility

The system runs today with zero credentials in mock mode.

| Requirement | Status | Notes |
|---|---|---|
| Python runtime | Python 3.11+ | Running |
| FAISS in-process vector store | Deployed | No external dependency |
| MS Learn MCP | Public endpoint | Live and tested — no auth required |
| watsonx Orchestrate | Configured | Deployed instance |
| watsonx embeddings | Graceful fallback | Needs IAM key for semantic precision |
| Persistent sessions | In-memory per process | Redis for multi-instance scale |

---

## Real-World Impact

A [2023 Stack Overflow Developer Survey](https://survey.stackoverflow.co/2023/) found developers spend ~25% of their working day searching documentation. For 50+ technical staff, that is thousands of hours per year producing no business value.

Intently compresses that to minutes:

- A developer configuring OAuth 2.0 for Node.js gets a typed, structured, annotated code example built from real MS Learn docs — in one interaction.
- An IT admin enabling MFA for Azure AD gets a numbered prerequisite list and step sequence from the exact Conditional Access documentation page.
- A new team member who doesn't know where to start gets 3–5 contextual angles on their question and can pick the one that matches their mental model.

The architecture — **intent-driven retrieval with typed content representation** — is reusable across any documentation corpus: internal wikis, compliance libraries, support knowledge bases, product manuals.

---

## How IBM Bob Was Used

IBM Bob was the **primary development environment** for every file in this repository — not a suggestion tool alongside other tools, but the sole environment in which all architecture decisions, code, tests, and documentation were produced.

| Phase | What Bob did |
|---|---|
| Architecture | Designed the two-layer conversation pattern, three-agent pipeline, and queryFocus contract |
| Intent Agent | Wrote the scorer, entity classifier, smart-casing system, and Layer 1 option builder |
| Retrieval Agent | Built MCP session management, multi-query expansion, FAISS upsert/rerank, and queryFocus extraction |
| Content Agent | Built DITA-typed content synthesis, insight block, code extraction, and strict Layer 2 contract |
| Orchestrate | Wrote and refined the system instructions deployed to watsonx Orchestrate |
| API server | Built all FastAPI endpoints, `.env` loader, Orchestrate proxy, and health endpoint |
| UI | Built the full Carbon Design System enterprise UI |
| Git | Configured the remote, managed all commits and pushes |
| Documentation | Authored this README in full |

---

<p align="center">Intently — Conversation Precision by Design · IBM AI Builders Challenge · August Wildcard · Built with IBM Bob</p>
