# Conversation Design Assistant

> **AI Builders Challenge — July 2025**
> **Theme: AI Co-Workers & Decision Intelligence**
> Built entirely with IBM Bob

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![MS Learn MCP](https://img.shields.io/badge/retrieval-MS%20Learn%20MCP-0078d4)](https://learn.microsoft.com)
[![watsonx](https://img.shields.io/badge/AI-IBM%20watsonx-0f62fe)](https://www.ibm.com/watsonx)
[![Built with IBM Bob](https://img.shields.io/badge/built%20with-IBM%20Bob-0f62fe)](http://ibm.biz/university-bob)

---

## Problem Statement

Content teams, developers, and IT administrators spend hours hunting through sprawling documentation portals, policy libraries, and technical reference sites — only to come up empty, reformulate manually, and eventually give up or escalate to an expert. Even when the answer exists, the path to it is broken.

The problem has three compounding layers:

1. **No intent understanding** — keyword search returns noise. Users must already know exactly what to search for, penalising anyone new to a topic.
2. **No iterative refinement** — when the first result misses, the system abandons the user. There is no intelligent next step.
3. **No empathetic guidance** — users are left alone at the moment they need help most, with no path forward except giving up or waiting for a human.

This project solves all three — and goes further.

---

## Solution Description

The **Conversation Design Assistant** is an autonomous multi-agent system that turns a natural-language question into a structured, confidence-scored, accessibility-validated answer — backed by real Microsoft Learn documentation, enriched with multimedia, and guided by empathetic interactive choices.

The user never has to reformulate a search manually. The system iterates for them, getting smarter with every loop, until the right answer is found or a human steps in.

### Key user-facing behaviours

- **Intent-first** — understands what you mean, not just what you typed. Asks targeted clarifying questions only when genuinely ambiguous.
- **Synthesised answers** — returns step-by-step guides, code snippets, policy summaries, or FAQ cards depending on the question type. Never a raw list of links.
- **Multimedia-enriched** — embeds diagrams, screenshots, and MS Learn video links directly from source documentation so context is never lost.
- **Empathetic navigation** — always offers **"Show me next"** or **"This doesn't help"** — friendly, never technical. After 5 iterations, **"Contact support"** and **"Get human help"** appear. Never before.
- **Confidence-transparent** — every response carries a `High / Medium / Low` confidence rating so users and integrators always know how much to trust the answer.
- **Automatic escalation** — routes to human review when confidence is low and `humanReviewOnLowConfidence` is set.

---

## Out-of-the-Box Benefits

### Zero hallucination risk

Every answer is **grounded exclusively in retrieved Microsoft Learn documentation**. The system never generates facts from model weights alone. The watsonx summary block is generated from retrieved chunk text — not from imagination. If retrieval returns nothing confident, the system says so and offers refinements instead of inventing an answer.

> Sources are always cited. Every response includes a `## Sources` section with the exact MS Learn URL and a confidence score. Users can verify every claim in one click.

### No off-track inputs

The Intent & Clarification Agent gates every query before retrieval runs. If a query is too vague, too ambiguous, or doesn't map to a recognisable intent, the system asks a targeted clarifying question instead of guessing. The retrieval agent only runs when intent is clear. This means:

- No wasted API calls on nonsense inputs
- No confabulated answers to out-of-scope queries
- No silent failures — every response is either an answer, a clarification request, or an honest low-confidence disclosure

### Richer user experience through multimedia

Content doesn't stop at text. The system scans every retrieved documentation chunk for:

- **Images and diagrams** — architecture diagrams, flow charts, and screenshots embedded directly into the response with descriptive alt text
- **MS Learn module links** — structured learning paths and video modules surfaced as clickable media cards
- **YouTube embeds** — official Microsoft demo videos linked inline where sources provide them

Users get the same experience they would browsing docs manually — minus the hunt.

### Narrowing the search on every iteration

The feedback loop is not a re-run of the same query. Each iteration actively improves:

- The **Intent Agent** sharpens the `queryFocus` using the full history of prior queries
- The **Retrieval Agent** alternates MCP strictness (odd iterations → stricter, even → broader) to explore different result bands
- The **FAISS index accumulates** — every loop adds new chunks to the in-memory index, so re-ranking draws from a growing, session-specific pool
- The result set is always fresh — the Content Agent selects the top 1–3 chunks from the re-ranked pool, which may differ from the previous iteration

The system gets smarter with each "Show me next" — not just louder.

### Interactivity with the entire Microsoft Learn docs set

The retrieval layer is connected directly to the **Microsoft Learn MCP API** — a live, authoritative index of the full Microsoft/Azure documentation corpus. This means:

- Results are always current — no stale cache, no outdated snapshots
- Coverage spans Azure, Microsoft 365, Intune, Power Platform, GitHub, and all other MS Learn properties
- The `microsoft_code_sample_search` tool is invoked separately for code-heavy queries, retrieving official runnable code examples alongside prose documentation
- Two tools run in parallel for developer queries: docs search + code sample search

### Structured, validated output every time

Every response is validated before it reaches the user:

| Check | What it verifies |
|---|---|
| `clarityScore (0–5)` | Avg sentence length ≤ 20 words, active voice, headings present |
| `concisionScore (0–5)` | Content within `maxLength`, further rewarded at ≤ 80% of limit |
| `accessibilityPass` | Headings present, lists for step formats, no bare URLs, all images have alt text, all option labels ≤ 40 chars |

Integrators receive the full `validationReport` with every response — ready to gate publishing workflows or trigger human review.

---

## AI Approach and Architecture

The system is a **three-agent pipeline** driven by a **watsonx Orchestrator**. Each agent is a specialist. The orchestrator drives them in sequence and owns the feedback loop.

```
User Input JSON
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                    WatsonxOrchestrator                        │
│                                                              │
│  sessionStore: { mcpSessionId, faissIndex,                   │
│                  iterationCount, priorQueries }               │
│                                                              │
│  ┌───────────────────────────────────────┐                   │
│  │  Agent 1 — Intent & Clarification     │                   │
│  │  Rule-based keyword scoring           │                   │
│  │  Detects ambiguity → ask or proceed   │                   │
│  │  Loop re-entry: sharpens queryFocus   │                   │
│  └──────────────────┬────────────────────┘                   │
│                     │ status: proceed                         │
│  ┌──────────────────▼────────────────────┐                   │
│  │  Agent 2 — Information Retrieval      │                   │
│  │  MS Learn MCP: docs + code search     │                   │
│  │  watsonx slate-30m embeddings         │                   │
│  │  Per-session FAISS re-ranking         │                   │
│  │  Alternating strictness per loop      │                   │
│  └──────────────────┬────────────────────┘                   │
│                     │ results + avgScore                      │
│  ┌──────────────────▼────────────────────┐                   │
│  │  Agent 3 — Content Representation     │                   │
│  │  watsonx Granite summary block        │                   │
│  │  Format: steps / code / summary / faq │                   │
│  │  Multimedia: images + video links     │                   │
│  │  Empathetic interactive options       │                   │
│  │  validationReport per response        │                   │
│  └──────────────────┬────────────────────┘                   │
│                     │                                         │
│             AgentOutput JSON                                  │
│                     │                                         │
│  User picks "Show me next" ─────────────────────────┐        │
│                     │                       loop++  │        │
│  User satisfied / "Contact support" (iter ≥ 5)      │        │
└──────────────────────────────────────────────────────────────┘
```

### Feedback loop — how it gets smarter

| Iteration | Intent Agent | Retrieval Agent | FAISS Index | Options shown |
|---|---|---|---|---|
| 1 | Score intent, extract entities | MCP search, strictness=2 | 3–5 chunks | Show me next, This doesn't help |
| 2 | Sharpen queryFocus using prior query | MCP search, strictness=3 | 6–10 chunks | Show me next, This doesn't help |
| 3 | Sharpen again | MCP search, strictness=2 | 9–15 chunks | Show me next, This doesn't help |
| … | … | … | Grows each iteration | … |
| 5+ | Sharpen | Alternate strictness | Accumulated | + Contact support, Get human help |

### AI components

| Component | Technology | Role |
|---|---|---|
| Intent scoring | Rule-based Python | Keyword overlap, relative normalisation, ambiguity detection |
| Document retrieval | MS Learn MCP `microsoft_docs_search` | Live authoritative Microsoft documentation |
| Code retrieval | MS Learn MCP `microsoft_code_sample_search` | Official runnable code examples |
| Embeddings | watsonx `ibm/slate-30m-english-rtrvr` | Semantic chunk encoding (falls back gracefully) |
| Vector store | FAISS `IndexFlatIP` in-memory | Cosine-similarity re-ranking across session |
| Content generation | watsonx `ibm/granite-13b-chat-v2` | Plain-language summary block |
| Orchestration | Python `WatsonxOrchestrator` | Session state, loop control, routing |
| Validation | Deterministic Python | `clarityScore`, `concisionScore`, `accessibilityPass` |

### Output schema

```json
{
  "sessionId":           "string",
  "responseType":        "answer | clarify | low_confidence",
  "responseText":        "empathetic 1–2 sentence summary",
  "format":              "steps | faq | code_snippet | summary",
  "content":             "markdown — insight block, body, media, sources",
  "interactiveOptions": [
    { "id": "show_next",    "label": "Show me next",     "description": "See more results about {topic}" },
    { "id": "doesnt_help", "label": "This doesn't help", "description": "Try a different angle on {topic}" }
  ],
  "sources":             [{ "file_path": "learn.microsoft.com/...", "score": 0.91 }],
  "confidence":          "High | Medium | Low",
  "mcpSessionId":        "string — reused across loop iterations",
  "suggestedRefinements":["narrower query", "broader query"],
  "routeToHumanReview":  false,
  "estimatedReadTime":   "2 min read",
  "validationReport":    { "clarityScore": 5, "concisionScore": 3, "accessibilityPass": true }
}
```

---

## Selected Challenge Theme

**AI Co-Workers & Decision Intelligence**

| Challenge question | How this project answers it |
|---|---|
| **How can AI reduce repetitive work?** | Developers and admins no longer reformulate queries or trawl docs manually. The system iterates on their behalf, getting smarter each loop. |
| **How can AI improve decision-making?** | Every response carries a confidence level, a `validationReport`, and a clear escalation path. Teams know exactly when to trust the AI and when to bring in a human. |
| **How can AI help teams achieve outcomes faster?** | The feedback loop means the user's first query is never their last attempt. From first question to verified answer — no context switching, no tab hunting. |

This is not an AI that searches. It is an AI co-worker that **understands, retrieves, synthesises, validates, and guides** — and knows when to hand off.

---

## Repository Structure

```
conversation_agent/
  __init__.py          — package marker
  schemas.py           — Pydantic v2 models: AgentInput, AgentOutput, SessionStore
  intent_agent.py      — Agent 1: intent scoring, clarification, loop sharpening
  retrieval_agent.py   — Agent 2: MS Learn MCP + FAISS RAG pipeline
  content_agent.py     — Agent 3: synthesis, multimedia, empathetic UX, validation
  orchestrator.py      — WatsonxOrchestrator: loop controller, session manager
  .env.example         — environment variable template (no secrets)

agent_prompt.md           — canonical system prompt spec, tagged v1.0
test_runner.py            — runs Test A (×2 iterations), B, C end-to-end
conversation-agent-plan.md — full build plan v3

test_outputs/
  test_a_output.json        — Test A live output (iteration 1, real MS Learn)
  test_a_loop2_output.json  — Test A live output (iteration 2, FAISS accumulated)
  test_b_output.json        — Test B live output (clarify path)
  test_c_output.json        — Test C live output (live policy content)
  baseline_test_a/b/c.json  — hand-crafted baseline expectations

validation/
  validate_outputs.py    — post-hoc schema + accessibility + routing validator
  validation_report.json — latest results: 4/4 PASS
```

---

## Getting Started

### Prerequisites

```
Python 3.11+
pip install faiss-cpu numpy requests python-dotenv pydantic
```

### Quick start — Mock Mode (no credentials needed)

```bash
git clone https://github.com/DipeshC-git/interactive-conversation-design-assistant.git
cd interactive-conversation-design-assistant

pip install faiss-cpu numpy requests python-dotenv pydantic

cp conversation_agent/.env.example conversation_agent/.env
# MOCK_MODE=true is the default — no changes needed

python test_runner.py          # runs all test cases
python validation/validate_outputs.py  # validates outputs
```

### Live Mode — real MS Learn content (no API key needed for MCP)

```bash
# Edit conversation_agent/.env:
MOCK_MODE=false
# Leave WATSONX_* blank — MCP retrieval works without credentials
# watsonx calls fall back gracefully to template summaries

python test_runner.py
```

### Full Live Mode — with watsonx generation + embeddings

```bash
# For standard IBM Cloud watsonx.ai:
WATSONX_API_KEY=<your-ibm-cloud-iam-key>
WATSONX_PROJECT_ID=<your-project-id>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
MOCK_MODE=false

# For Watson Orchestrate:
WATSONX_BEARER_TOKEN=<session-bearer-from-devtools>
WATSONX_URL=https://api.<region>.dl.watson-orchestrate.ibm.com/instances/<id>
MOCK_MODE=false
```

### Use the orchestrator in your own code

```python
from conversation_agent.orchestrator import WatsonxOrchestrator
from conversation_agent.schemas import AgentInput

orch = WatsonxOrchestrator()

# First turn
inp = AgentInput(
    sessionId="session-001",
    userInput="How do I configure OAuth 2.0 for Azure AD in Node.js?",
    audience="developer",
)
out = orch.run(inp)
print(out.responseType, out.confidence)
print(out.content)

# User picks "Show me next" — loop re-entry
out2 = orch.run_loop(inp, feedback="show_next")
print(out2.content[:200])
```

---

## Test Cases and Live Results

| Test | Input | Expected behaviour | Live result |
|---|---|---|---|
| **A iter 1** | `"How do I configure OAuth 2.0 for Azure AD in Node.js?"` | `answer`, `code_snippet`, High/Medium confidence, real MS Learn sources | ✅ `answer`, `Medium`, Azure AD B2C Node.js article |
| **A iter 2** | Same session — user picks `"Show me next"` | `answer`, FAISS index larger, `High` confidence | ✅ `answer`, `High`, FAISS grew to 4 chunks |
| **B** | `"How do I set up authentication?"` | `clarify`, two questions, three suggested actions | ✅ `clarify` as expected |
| **C** | `"Show me Contoso device reset policy"` | Retrieval; live MS Learn content returned | ✅ `answer`, `High`, real policy content |

**Validation: 4/4 outputs PASS** across 6 check categories:
`schema` · `loop_options` · `accessibility` · `routing` · `loop_marker` · `sources`

---

## How IBM Bob Was Used

IBM Bob was the **sole development environment** for this project — every file, every decision, every fix.

| Phase | What Bob did |
|---|---|
| **Architecture & planning** | Led three rounds of clarifying questions to define the loop mechanics, escalation gate, empathetic UX, and RAG approach. Authored the full build plan (`conversation-agent-plan.md`) across v1 → v2 → v3. |
| **Schema design** | Designed all Pydantic v2 models including `SessionStore` loop state, `InteractiveOption` label-length guard, and `ValidationReport`. |
| **Agent implementation** | Wrote all four Python modules. Fixed the intent scoring normalisation bug, the FAISS mock score restoration, the `links` list index error, and the MCP SSE parsing issue — all in-loop during testing. |
| **MCP integration** | Discovered the correct MS Learn MCP protocol (JSON-RPC over SSE), identified the actual tool names (`microsoft_docs_search`, `microsoft_code_sample_search`), and debugged the empty-body 200 response. |
| **Credential diagnostics** | Decoded the ZenApiKey format, identified the Watson Orchestrate SSO proxy boundary, and implemented graceful fallbacks for both embeddings and generation. |
| **Git workflow** | Initialised the repo, diagnosed the PAT scope gap, force-pushed the corrected branch, and scoped every commit to exactly the right files. |
| **Testing & validation** | Wrote all smoke tests, the test runner, and the validation script. All bugs surfaced during testing were diagnosed and fixed by Bob within the same session. |
| **Documentation** | Authored this README, `agent_prompt.md` v1.0, and `conversation-agent-plan.md`. |

> Every line of code, every architectural decision, and every commit in this repository was produced through conversation with IBM Bob.

---

## Roadmap

| Next step | Description |
|---|---|
| IBM Cloud IAM key | Unlocks full watsonx Granite generation + slate-30m embeddings |
| Streaming responses | Stream content tokens as they generate — lower perceived latency |
| UI layer | Streamlit or React frontend wired to the orchestrator |
| Persistent sessions | Store `sessionStore` in Redis or Cloudant across page reloads |
| Multi-corpus support | Add connectors for SharePoint, Confluence, and internal knowledge bases |
| Evaluation harness | Compare baseline vs loop-refined outputs with RAGAS or similar |

---

<p align="center">Built with <strong>IBM Bob</strong> · AI Builders Challenge July 2025</p>
