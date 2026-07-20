# Conversation Design Assistant

> **AI Builders Challenge — July 2025**
> Theme: AI Co-Workers & Decision Intelligence
> Built entirely with IBM Bob

---

## Problem Statement

Content teams, developers, and IT administrators spend hours hunting through sprawling documentation portals, policy libraries, and technical reference sites to answer questions they encounter daily. When results are ambiguous, they have to reformulate queries manually, often giving up and escalating to a human expert — even when the answer exists somewhere in the docs.

The core problem is threefold:

1. **No intent understanding** — keyword search returns noise; users must already know exactly what to search for.
2. **No iterative refinement** — when the first result misses, there is no intelligent next step.
3. **No empathetic guidance** — users are left alone when confidence is low, with no path forward except giving up.

This project solves all three.

---

## Solution Description

The **Conversation Design Assistant** is an autonomous multi-agent system that turns a user's natural-language question into a structured, confidence-scored, accessibility-validated answer — complete with code examples, multimedia, and empathetic navigation options.

The user never has to reformulate a search manually. The system does it for them, iterating intelligently until the user finds what they need or chooses to escalate to a human.

**Key user-facing behaviours:**

- Asks targeted clarifying questions only when a query is genuinely ambiguous
- Returns synthesised answers with code snippets, step-by-step guides, or policy summaries depending on the question type
- Embeds images, diagrams, and MS Learn video links from source documentation
- Always offers friendly next steps: **"Show me next"** or **"This doesn't help"**
- After 5 refinement iterations, surfaces **"Contact support"** and **"Get human help"** — never before, so users are never pressured to escalate prematurely
- Routes automatically to human review when confidence is low and `humanReviewOnLowConfidence` is set

---

## AI Approach and Architecture

The system is built as a **three-agent pipeline** orchestrated by a **watsonx Orchestrator**. Each agent is a specialist. The orchestrator drives them in sequence and controls the feedback loop.

```
User Input JSON
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                   WatsonxOrchestrator                        │
│                                                             │
│  sessionStore: { mcpSessionId, faissIndex,                  │
│                  iterationCount, priorQueries }              │
│                                                             │
│  ┌──────────────────────────────────────┐                   │
│  │  Agent 1: Intent & Clarification     │                   │
│  │  - Rule-based keyword scoring        │                   │
│  │  - Detects ambiguity → ask or proceed│                   │
│  │  - Loop re-entry: sharpens query     │                   │
│  └──────────────┬───────────────────────┘                   │
│                 │ status: proceed                            │
│  ┌──────────────▼───────────────────────┐                   │
│  │  Agent 2: Information Retrieval      │                   │
│  │  - MS Learn MCP search_hybrid        │                   │
│  │  - watsonx embeddings (slate-30m)    │                   │
│  │  - Per-session FAISS re-ranking      │                   │
│  │  - Alternating strictness per loop   │                   │
│  └──────────────┬───────────────────────┘                   │
│                 │ results + avgScore                         │
│  ┌──────────────▼───────────────────────┐                   │
│  │  Agent 3: Content Representation     │                   │
│  │  - watsonx summary (Granite)         │                   │
│  │  - Markdown synthesis (steps/code/   │                   │
│  │    summary/faq)                      │                   │
│  │  - Multimedia: images + video links  │                   │
│  │  - Empathetic interactive options    │                   │
│  │  - validationReport (clarity,        │                   │
│  │    concision, accessibility)         │                   │
│  └──────────────┬───────────────────────┘                   │
│                 │                                            │
│         AgentOutput JSON                                     │
│                 │                                            │
│   User picks "Show me next" ──────────────────────┐         │
│                 │                         loop++  │         │
│   User satisfied / picks "Contact support"        │         │
└─────────────────────────────────────────────────────────────┘
```

### The Feedback Loop

The loop has **no hard cap**. Each iteration:

| Step | What changes |
|---|---|
| Intent Agent | Sharpens `queryFocus` using prior query history — never re-asks clarifying questions |
| Retrieval Agent | Alternates MCP strictness (odd→3, even→2); upserts new chunks into the FAISS index |
| FAISS index | Accumulates chunks across iterations — re-ranking improves with each loop |
| Content Agent | Synthesises fresh content from the re-ranked pool; marks result set number |
| Options | `"Contact support"` and `"Get human help"` appear only after 5 iterations |

### AI Components

| Component | Technology | Role |
|---|---|---|
| Intent scoring | Rule-based Python (keyword overlap, relative normalisation) | Intent detection, entity extraction, clarification |
| Document retrieval | [MS Learn MCP API](https://learn.microsoft.com/api/mcp) `search_hybrid` | Fetches real Microsoft documentation chunks |
| Embeddings | watsonx `ibm/slate-30m-english-rtrvr` | Encodes chunks and queries for semantic similarity |
| Vector store | FAISS `IndexFlatIP` (in-memory, per-session) | Cosine-similarity re-ranking across accumulated chunks |
| Content generation | watsonx `ibm/granite-13b-chat-v2` | Plain-language summary block injected into every response |
| Orchestration | IBM watsonx Orchestrator (Python) | Drives agent pipeline, manages session state, controls loop |
| Validation | Deterministic Python checks | `clarityScore`, `concisionScore`, `accessibilityPass` per response |

### Output Schema (per response)

```json
{
  "sessionId": "string",
  "responseType": "answer | clarify | low_confidence",
  "responseText": "empathetic 1–2 sentence summary",
  "format": "steps | faq | code_snippet | summary",
  "content": "full markdown with summary block, multimedia, sources",
  "interactiveOptions": [
    { "id": "show_next",     "label": "Show me next",      "description": "context-aware" },
    { "id": "doesnt_help",  "label": "This doesn't help", "description": "context-aware" }
  ],
  "sources": [{ "file_path": "string", "score": 0.0 }],
  "confidence": "High | Medium | Low",
  "suggestedRefinements": ["narrower query", "broader query"],
  "routeToHumanReview": false,
  "estimatedReadTime": "2 min read",
  "validationReport": { "clarityScore": 5, "concisionScore": 3, "accessibilityPass": true }
}
```

---

## Selected Challenge Theme

**AI Co-Workers & Decision Intelligence**

This project directly addresses two challenge themes:

- **AI Co-Workers** — The system acts as a tireless documentation assistant that understands intent, asks smart questions, retrieves and synthesises knowledge, and guides users toward the right answer without human intervention.
- **Decision Intelligence** — Confidence scoring, `routeToHumanReview` routing, and the iteration-5 escalation gate give teams structured signals about when AI can answer autonomously vs. when a human expert should step in.

**How it reduces repetitive work:** Developers and admins no longer manually reformulate queries or trawl through documentation pages. The system iterates on their behalf.

**How it improves decision-making:** Every response includes a confidence level (`High / Medium / Low`), a `validationReport`, and a clear escalation path — giving teams the information to act or escalate with confidence.

**How it helps teams achieve outcomes faster:** The feedback loop means the user's first query is never their last attempt. The system keeps refining until the answer is found or a human takes over.

---

## Repository Structure

```
conversation_agent/
  __init__.py          — package marker
  schemas.py           — Pydantic v2 models: AgentInput, AgentOutput, SessionStore
  intent_agent.py      — Agent 1: intent scoring, clarification, loop sharpening
  retrieval_agent.py   — Agent 2: MS Learn MCP + watsonx FAISS RAG pipeline
  content_agent.py     — Agent 3: content synthesis, multimedia, empathetic UX
  orchestrator.py      — WatsonxOrchestrator: loop controller, session manager
  .env.example         — environment variable template (no secrets)

agent_prompt.md        — canonical system prompt spec, tagged v1.0
test_runner.py         — runs Test A (×2 iterations), B, C end-to-end
conversation-agent-plan.md — full build plan v3

test_outputs/
  test_a_output.json        — Test A real output (iteration 1)
  test_a_loop2_output.json  — Test A real output (iteration 2, loop)
  test_b_output.json        — Test B real output (clarify path)
  test_c_output.json        — Test C real output (low confidence path)
  baseline_test_a/b/c.json  — hand-crafted baseline expectations

validation/
  validate_outputs.py    — post-hoc schema + accessibility + routing validator
  validation_report.json — latest validation results (4/4 PASS)
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- `pip install faiss-cpu numpy requests python-dotenv pydantic`
- IBM watsonx credentials (optional — see Mock Mode below)

### Quick start — Mock Mode (no credentials needed)

```bash
# 1. Clone the repo
git clone https://github.com/DipeshC-git/interactive-conversation-design-assistant.git
cd interactive-conversation-design-assistant

# 2. Install dependencies
pip install faiss-cpu numpy requests python-dotenv pydantic

# 3. Copy env template — leave MOCK_MODE=true
cp conversation_agent/.env.example conversation_agent/.env

# 4. Run the test suite
python test_runner.py

# 5. Validate outputs
python validation/validate_outputs.py
```

### Live Mode (with watsonx credentials)

```bash
# Edit conversation_agent/.env:
WATSONX_API_KEY=<your-key>
WATSONX_PROJECT_ID=<your-project-id>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_BEARER_TOKEN=<bearer-token-for-watson-orchestrate>
MOCK_MODE=false

# Run
python test_runner.py
```

> MS Learn MCP requires no API key — it is a public endpoint.
> The Bearer token is only required for Watson Orchestrate deployments.
> For standard IBM Cloud watsonx.ai, the `WATSONX_API_KEY` alone is sufficient.

### Use the orchestrator directly

```python
from conversation_agent.orchestrator import WatsonxOrchestrator
from conversation_agent.schemas import AgentInput

orch = WatsonxOrchestrator()

# First turn
out = orch.run(AgentInput(
    sessionId="session-001",
    userInput="How do I configure OAuth 2.0 for Azure AD in Node.js?",
    audience="developer"
))
print(out.responseType, out.confidence)
print(out.content)

# Loop re-entry when user picks "Show me next"
out2 = orch.run_loop(inp, feedback="show_next")
```

---

## Test Cases and Outputs

| Test | Input | Expected | Result |
|---|---|---|---|
| **A** (iter 1) | `"How do I configure OAuth 2.0 for Azure AD in Node.js?"` | `answer`, `code_snippet`, High confidence | ✅ Pass |
| **A** (iter 2) | Same session, user picks `"Show me next"` | `answer`, loop marker in content, FAISS index grows | ✅ Pass |
| **B** | `"How do I set up authentication?"` | `clarify`, two questions, three suggested actions | ✅ Pass |
| **C** | `"Show me Contoso device reset policy"` | `low_confidence`, `suggestedRefinements`, `routeToHumanReview: true` | ✅ Pass |

**Validation: 4/4 outputs PASS** across 6 check categories:
`schema` · `loop_options` · `accessibility` · `routing` · `loop_marker` · `sources`

---

## How IBM Bob Was Used

IBM Bob was the **sole development environment** for this entire project — from initial concept to final commit.

| Phase | How Bob was used |
|---|---|
| **Architecture & planning** | Bob led an interactive planning session, asking targeted clarifying questions about the loop mechanics, escalation gate, empathetic UX, and RAG approach. The full build plan (`conversation-agent-plan.md`) was authored and iterated by Bob across three versions (v1 → v2 → v3). |
| **Schema design** | Bob designed all Pydantic v2 models (`schemas.py`) including the `SessionStore` loop state, `InteractiveOption` label-length guard, and `ValidationReport` structure. |
| **Agent implementation** | All four Python modules (`intent_agent.py`, `retrieval_agent.py`, `content_agent.py`, `orchestrator.py`) were written, debugged, and validated by Bob — including fixing the intent scoring normalisation, FAISS mock score restoration, and link-list edge cases. |
| **Credential diagnostics** | Bob probed the Watson Orchestrate authentication flow, decoded the ZenApiKey format, identified the SSO proxy blocker, and guided the setup of mock-to-live credential switching. |
| **Testing & validation** | Bob wrote all smoke tests, the test runner, and the validation script. When tests revealed bugs (e.g. the intent delta threshold, the IndexError on empty `links` list), Bob diagnosed and fixed them in-loop. |
| **Git workflow** | Bob managed the entire git workflow: initialised the repo, identified the PAT scope gap, wrote the fix guide, force-pushed the corrected branch, and scoped each commit to exactly the right files. |
| **Documentation** | This README, `agent_prompt.md` (v1.0), and `conversation-agent-plan.md` were all authored by Bob. |

> Every line of code, every commit, and every design decision in this repository was produced through a conversation with IBM Bob.

---

## License

MIT — see [LICENSE](LICENSE) if present, or assume open use for challenge purposes.

---

<p align="center">Built with <strong>IBM Bob</strong> · AI Builders Challenge July 2025</p>
