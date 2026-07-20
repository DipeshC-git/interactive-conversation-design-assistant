# Conversation Design Assistant — Build Plan (v3)

## Top-Level Overview

Build a **multi-agent Conversation Design Assistant** as a parallel, self-contained module
inside the existing repo. The PDF pipeline is left completely untouched. All new files live
under `conversation_agent/`, `test_outputs/`, and `validation/` at the repo root.

The system has **three specialist agents** driven by a **watsonx Orchestrator**:

| Agent | Role |
|---|---|
| **Intent & Clarification Agent** | Parses user input, scores intents, sharpens intent on loop re-entry, returns clarifying questions when confidence is low |
| **Information Retrieval Agent** | Calls MS Learn MCP `search_hybrid`, embeds chunks via watsonx embeddings, stores in per-session FAISS index, re-ranks on each loop iteration |
| **Content Representation Agent** | Synthesizes final markdown content, applies plain-language + accessibility rules, produces `validationReport` |

The **watsonx Orchestrator** is the loop controller. It drives agents in sequence, routes
`clarify` short-circuits, tracks iteration count, appends user feedback signals to the session,
and surfaces empathetic option labels that evolve as the user iterates — with human escalation
appearing only after 5 failed iterations.

---

## Architecture

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                        WatsonxOrchestrator                          │
 │                                                                     │
 │  sessionStore: { mcpSessionId, faissIndex, iterationCount,          │
 │                  priorIntents, priorQueries, userPreferences }       │
 │                                                                     │
 │  Input JSON ──► [1] Intent & Clarification Agent                    │
 │                        │                                            │
 │                        ├─ status:"clarify" ──► return clarify JSON  │
 │                        │                                            │
 │                        └─ status:"proceed"                          │
 │                               │                                     │
 │                    [2] Information Retrieval Agent                   │
 │                        ├─ MCP search_hybrid (requests)              │
 │                        ├─ watsonx embed chunks                      │
 │                        ├─ FAISS upsert + semantic re-rank           │
 │                        └─ returns results + avgScore                │
 │                               │                                     │
 │                    [3] Content Representation Agent                  │
 │                        ├─ synthesize content from top results       │
 │                        ├─ run validationReport checks               │
 │                        └─ always append interactiveOptions:         │
 │                             ["Refine search","Request human help"]  │
 │                               │                                     │
 │                    Assemble AgentOutput JSON                         │
 │                               │                                     │
 │         ◄──── User picks "Refine search" ────────────────────┐      │
 │                               │                              │      │
 │                    User satisfied OR picks                    │      │
 │                    "Request human help"                       │      │
 │                               │                              │      │
 │                          END / ESCALATE          LOOP (no cap)│      │
 └─────────────────────────────────────────────────────────────────────┘
```

### Loop Mechanics

| Event | Orchestrator Action |
|---|---|
| User picks `"Show me next"` / `"This doesn't help"` | Increment `iterationCount`. Append feedback signal to `sessionStore.priorQueries`. Re-invoke Intent Agent with `feedbackSignal` in input. |
| Intent Agent receives loop re-entry | Sharpens `chosenIntent` using `priorIntents` history; adjusts query focus. |
| Retrieval Agent on loop re-entry | Builds a new query variant (alternate strictness: odd → 3, even → 2). Upserts new MCP hits into session FAISS index. Re-ranks all accumulated chunks. |
| Content Agent on loop re-entry | Selects top 1–3 from re-ranked FAISS pool. Synthesizes fresh content including multimedia. Always re-appends empathetic loop options. |
| `iterationCount < 5` | Show only `"Show me next"` and `"This doesn't help"` — no human escalation option yet. |
| `iterationCount >= 5` | Add `"Contact support"` / `"Get human help"` option to `interactiveOptions`. |
| User picks `"Contact support"` / `"Get human help"` | Orchestrator sets `routeToHumanReview: true` and stops the loop. |

### Empathetic Option Label Design

Labels are **fixed friendly phrases** (≤40 chars, keyboard-navigable). The `description`
field is **context-aware** (ARIA-style, longer) and adapts to the topic.

| Iteration | Options shown | Label (fixed) | Description (context-aware) |
|---|---|---|---|
| 1–4 | Continue loop | `"Show me next"` | `"See more results about {topic}"` |
| 1–4 | Continue loop | `"This doesn't help"` | `"Tell us this missed the mark on {topic} and try a different angle"` |
| 5+ | Continue loop | `"Show me next"` | same as above |
| 5+ | Continue loop | `"This doesn't help"` | same as above |
| 5+ | Escalate | `"Contact support"` | `"Connect with a specialist who can help you with {topic}"` |
| 5+ | Escalate | `"Get human help"` | `"Escalate to a human reviewer for personalized assistance with {topic}"` |

`{topic}` = `chosenIntent` entity summary from the Intent Agent, injected at render time.

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffold & Dependencies

**Intent**
Create the folder structure and register new dependencies so all subsequent sub-tasks
have a stable, importable foundation.

**Expected Outcomes**
- `conversation_agent/` package exists with `__init__.py`
- `conversation_agent/schemas.py` defines all Pydantic v2 models for Input and Output
- `test_outputs/` and `validation/` folders exist
- `pyproject.toml` updated with new optional dep group `[conversation-agent]`

**Todo List**
1. Create `conversation_agent/__init__.py` — empty, marks package
2. Create `conversation_agent/schemas.py` with Pydantic v2 models:
   - `SessionStore` — `mcpSessionId`, `iterationCount: int = 0`,
     `priorIntents: list[str] = []`, `priorQueries: list[str] = []`,
     `userPreferences: dict = {}`
   - `AgentInput` — full Input JSON schema fields including `feedbackSignal: str | None`
   - `InteractiveOption` — `id`, `label` (max 40 chars enforced), `description`
   - `Source` — `file_path`, `page_numbers`, `score: float`
   - `ValidationReport` — `clarityScore: int`, `concisionScore: int`, `accessibilityPass: bool`
   - `AgentOutput` — full Output JSON schema fields
3. Create `test_outputs/.gitkeep`
4. Create `validation/.gitkeep`
5. Add `[project.optional-dependencies]` group `conversation-agent` to `pyproject.toml`:
   - `ibm-watsonx-ai>=1.1.0`
   - `requests>=2.32.0`
   - `python-dotenv>=1.0.0`
   - `faiss-cpu>=1.8.0`
   - `numpy>=1.26.0`

**Relevant Context**
- Existing `schemas.py` at repo root is for the PDF pipeline — do NOT touch it
- `conversation_agent/schemas.py` is entirely separate
- `iterationCount` starts at 0 on first invocation, incremented by orchestrator on each loop

**Status** — `[ ] pending`

---

### Sub-Task 2 — Intent & Clarification Agent

**Intent**
Implement Agent 1. On first entry it parses `userInput` and scores intents using
keyword-pattern heuristics. On loop re-entry it receives `feedbackSignal` and
`priorIntents` from the orchestrator, sharpens the `chosenIntent`, and adjusts
the query focus before retrieval runs again.

**Expected Outcomes**
- `conversation_agent/intent_agent.py` implements `IntentAgent`
- `IntentAgent.run(input: AgentInput) -> dict` returns one of:
  - `{"status": "proceed", "chosenIntent": str, "intentScore": float, "entities": list[str], "needRetrieval": bool, "queryFocus": str}`
  - `{"status": "clarify", "clarifyingQuestions": list[str], "suggestedActions": list[str]}`
- On loop re-entry (`iterationCount > 0`): uses `priorIntents` + `priorQueries` to
  shift query focus (e.g. broaden scope, add technology qualifier)
- `needRetrieval = True` for: docs, code, how-to, policy, explicit doc reference
- Clarification fires when: top score < 0.75 OR two intents within 0.15 of each other
  AND `iterationCount == 0` (no clarify on loop re-entry — just sharpen and continue)

**Todo List**
1. Create `conversation_agent/intent_agent.py`
2. Define `INTENT_PATTERNS: dict[str, list[str]]` — intent name → keyword list:
   - `configure_oauth`, `setup_auth`, `policy_lookup`, `general_howto`,
     `code_request`, `concept_explain`, `troubleshoot`
3. Implement `_score_intents(user_input: str) -> list[dict]` — keyword overlap,
   normalized 0.0–1.0, sorted descending
4. Implement `_extract_entities(user_input: str) -> list[str]` — product names,
   technologies, action verbs via simple regex + allowlist
5. Implement `_needs_retrieval(intent: str, user_input: str) -> bool`
6. Implement `_sharpen_intent(intent_result: dict, input: AgentInput) -> str` —
   on re-entry, combine `chosenIntent` with last `priorQueries` entry to produce
   a refined `queryFocus` string
7. Implement `_build_clarifying_questions(intents: list) -> tuple[list[str], list[str]]`
   — up to 2 short questions + 3 suggestedActions ranked by relevance
8. Implement `run(input: AgentInput) -> dict` wiring all of the above:
   - If `inputType == "menu"`: treat `menuSelection` as explicit intent, score 1.0
   - If `iterationCount > 0`: call `_sharpen_intent`, skip clarify check, return proceed
   - Else: normal first-entry flow

**Relevant Context**
- No LLM call — rule-based Python only
- `queryFocus` is a synthesized string passed to the Retrieval Agent to build its MCP query
- Clarification is suppressed on loop re-entries so the loop never gets stuck asking questions

**Status** — `[ ] pending`

---

### Sub-Task 3 — Information Retrieval Agent (RAG)

**Intent**
Implement Agent 2 with a full RAG pipeline. It calls the MS Learn MCP `search_hybrid`
endpoint (via `requests`), embeds the returned chunks using watsonx embeddings, upserts
them into a per-session FAISS in-memory index, and performs semantic re-ranking to
select the most relevant chunks for the Content Agent. On each loop iteration the index
accumulates chunks, giving the re-ranker more material to work with.

**Expected Outcomes**
- `conversation_agent/retrieval_agent.py` implements `RetrievalAgent`
- `RetrievalAgent.run(intent_result: dict, input: AgentInput) -> dict` returns:
  ```
  {
    "results": list[dict],   # top re-ranked chunks
    "avgScore": float,
    "lowConfidence": bool,
    "suggestedRefinements": list[str],
    "mcpSessionId": str,
    "indexSize": int          # total chunks in FAISS index this session
  }
  ```
- MCP session initialized once, ID stored and reused across loop iterations
- Each loop iteration uses alternating strictness: odd → 3, even → 2
- FAISS index is per-session (stored in `sessionStore` as a serialized object)
- Re-ranked top 5 passed back; top 1–3 selected by Content Agent
- `lowConfidence = True` if `avgScore < 0.45`
- Two `suggestedRefinements` always generated (one narrower, one broader) for the
  `"Refine search"` loop path

**Todo List**
1. Create `conversation_agent/retrieval_agent.py`
2. Implement `_initialize_mcp_session() -> str`:
   - POST to `https://learn.microsoft.com/api/mcp` initialize endpoint
   - Return `Mcp-Session-Id` header value
   - Exponential backoff: 1s → 2s → 4s, max 3 retries
3. Implement `_build_query(intent_result: dict, input: AgentInput) -> str`:
   - Combine `queryFocus` (from intent agent) + `entities` + `audience`
   - Strip PII patterns (email, phone) before sending
   - If `iterationCount > 0`: incorporate last `priorQueries` entry to pivot the query
4. Implement `_call_search_hybrid(query: str, session_id: str, strictness: int) -> list[dict]`:
   - POST `https://learn.microsoft.com/api/mcp` with `tools/call`
   - Body: `{"name": "search_hybrid", "arguments": {"query": query, "top_n": 5, "strictness": strictness}}`
   - Headers: `{"X-Mcp-Session-Id": session_id, "Content-Type": "application/json"}`
   - Exponential backoff on HTTP errors
5. Implement `_map_results(raw_hits: list) -> list[dict]`:
   - Normalize to `{chunk_id, file_path, page_numbers, text, snippet, score}`
6. Implement `_embed_chunks(chunks: list[dict]) -> np.ndarray`:
   - Call watsonx `EmbeddingModels` (e.g. `ibm/slate-30m-english-rtrvr`) on `chunk["text"]`
   - Return numpy array shape `(n, embedding_dim)`
7. Implement `_upsert_faiss(embeddings: np.ndarray, chunks: list[dict], session_store: SessionStore)`:
   - If no index yet: create `faiss.IndexFlatIP` (inner-product for cosine sim)
   - Add new embeddings; store chunk metadata list in `session_store`
   - Save updated index back to `session_store`
8. Implement `_rerank(query: str, session_store: SessionStore, top_k: int = 5) -> list[dict]`:
   - Embed the query using same watsonx model
   - Run FAISS search against full session index
   - Return top_k chunks with updated scores
9. Implement `_compute_avg_score(results: list[dict]) -> float`
10. Implement `_suggest_refinements(query: str, intent: str) -> list[str]`:
    - One narrower: add specific technology/version qualifier
    - One broader: remove most specific entity
11. Implement `run(intent_result, input)` wiring all steps:
    - Guard: if not `needRetrieval` → return empty result
    - Get or initialize MCP session ID
    - Determine strictness from `iterationCount`
    - Call MCP → map results → embed → upsert FAISS → re-rank
    - Compute avgScore on re-ranked results
    - Return full result dict

**Relevant Context**
- watsonx embedding model: `ibm/slate-30m-english-rtrvr` via `ibm_watsonx_ai.foundation_models.embeddings`
- FAISS index lives in `sessionStore` across loop iterations; the orchestrator passes the
  same `sessionStore` object into every `run()` call
- `faiss-cpu` and `numpy` are in the new dep group
- No disk writes — all in-memory

**Status** — `[ ] pending`

---

### Sub-Task 4 — Content Representation Agent

**Intent**
Implement Agent 3. It takes re-ranked retrieval results, synthesizes original markdown
content (including multimedia from MCP sources and watsonx-generated summaries), applies
plain-language and accessibility rules, runs deterministic `validationReport` checks, and
surfaces empathetic, context-aware interactive options that evolve across loop iterations.

**Expected Outcomes**
- `conversation_agent/content_agent.py` implements `ContentAgent`
- `ContentAgent.run(retrieval_result: dict, intent_result: dict, input: AgentInput) -> dict`
  returns:
  ```
  {
    "responseText": str,          # empathetic 1–2 sentence plain-text summary
    "format": str,
    "content": str,               # full markdown with multimedia embeds
    "interactiveOptions": list[dict],
    "sources": list[dict],
    "confidence": str,
    "suggestedRefinements": list[str],
    "estimatedReadTime": str,
    "validationReport": dict
  }
  ```
- `interactiveOptions` always contains `"Show me next"` and `"This doesn't help"`
- `"Contact support"` and `"Get human help"` added only when `iterationCount >= 5`
- All labels ≤ 40 chars; descriptions are context-aware and mention `{topic}`
- Content includes: images (from MCP hits), video/media links, watsonx-generated plain-language summary block
- `confidence` correctly derived from `avgScore` thresholds

**Todo List**
1. Create `conversation_agent/content_agent.py`
2. Implement `_determine_confidence(avg_score: float) -> str`:
   - High: ≥ 0.7 — Medium: 0.45–0.69 — Low: < 0.45
3. Implement `_select_format(intent: str, preference: str | None) -> str`:
   - `userFormatPreference` overrides if present
   - `configure_oauth` / `code_request` → `"code_snippet"`
   - `general_howto` / `troubleshoot` → `"steps"`
   - `policy_lookup` → `"summary"`
   - `concept_explain` → `"faq"`
   - default → `"summary"`
4. Implement `_select_top_results(results: list, avg_score: float) -> list`:
   - Return top 1–3 if `avg_score >= 0.45`; else `[]`
5. Implement `_extract_multimedia(selected: list) -> dict`:
   - Scan each chunk's `file_path`, `text`, and `snippet` for:
     - **Image URLs** — regex for `.png`, `.jpg`, `.gif`, `.svg` patterns in text
     - **Video/media links** — detect MS Learn module URLs (`learn.microsoft.com/…`),
       YouTube embed URLs (`youtu.be`, `youtube.com/embed`)
   - Return `{"images": [{"url": str, "alt": str}], "videos": [{"url": str, "title": str}]}`
   - For each image, generate a descriptive `alt` text from surrounding chunk text
6. Implement `_call_watsonx_summary(selected: list, intent: str, model) -> str`:
   - Call watsonx `ModelInference.generate_text()` with a short prompt:
     `"Summarize the following in 2–3 plain-language sentences for a {audience}: {chunk_text}"`
   - Return the generated summary string
   - Fallback: if watsonx call fails, use first 150 words of top chunk text
7. Implement `_synthesize_content(selected, intent_result, input, fmt, multimedia, watsonx_summary) -> str`:
   - Build markdown:
     - Open with watsonx-generated summary block (`> 💡 {watsonx_summary}`)
     - `steps`: `## Steps` heading + numbered list + commands + prerequisites
     - `code_snippet`: fenced block + inline comments + security note if secrets present
     - `summary`: `## Summary` heading + paragraph
     - `faq`: `## FAQ` heading + Q&A pairs
   - After main content, inject `## Media` section:
     - Each image: `![{alt}]({url})` with alt text
     - Each video: `▶ [{title}]({url})` as a descriptive link
   - Append `## Sources` with `file_path` and `score`
   - Respect `maxLength` — truncate with `> *[See more…]*` if over limit
   - On `iterationCount > 0`: prepend `> *Showing result set {n} — refined for you*`
8. Implement `_low_confidence_response(refinements: list[str], topic: str) -> str`:
   - Empathetic message: `"We couldn't find a confident answer about {topic} yet."`
   - Bullet list of `suggestedRefinements`
9. Implement `_build_interactive_options(intent_result: dict, iteration: int) -> list[dict]`:
   - Extract `topic` from `intent_result["entities"]` (first 1–2 joined)
   - Always include:
     - `{"id": "show_next", "label": "Show me next", "description": f"See more results about {topic}"}`
     - `{"id": "doesnt_help", "label": "This doesn't help", "description": f"Tell us this missed the mark on {topic} and try a different angle"}`
   - If `iteration >= 5`, also append:
     - `{"id": "contact_support", "label": "Contact support", "description": f"Connect with a specialist who can help you with {topic}"}`
     - `{"id": "get_human_help", "label": "Get human help", "description": f"Escalate to a human reviewer for personalized assistance with {topic}"}`
   - Enforce all labels ≤ 40 chars
10. Implement `_estimate_read_time(text: str) -> str` — word count ÷ 200 wpm, ceil, `"X min read"`
11. Implement `_run_validation(content: str, fmt: str, max_length: int) -> dict`:
    - `clarityScore (0–5)`: avg sentence ≤ 20 words → +2; no passive voice → +2; headings present → +1
    - `concisionScore (0–5)`: within `maxLength` → +3; ≤ 80% of limit → +2 more
    - `accessibilityPass`: headings present + lists for steps fmt + no bare URLs + all labels ≤ 40 + all images have alt text
12. Implement `run()` wiring all steps

**Relevant Context**
- Uses watsonx `ModelInference` for the summary block — first real LLM call in the pipeline
- Multimedia: images and video links extracted from MCP chunk text; embedded with accessibility rules
- The loop is sustained by always including `"Show me next"` in `interactiveOptions`
- Human escalation options appear only at `iterationCount >= 5`
- `responseText` is an empathetic plain-text opener (e.g. `"Here's what we found about OAuth 2.0 in Azure AD."`)

**Status** — `[ ] pending`

---

### Sub-Task 5 — watsonx Orchestrator (Loop Controller)

**Intent**
Implement the orchestrator that drives the three agents in sequence and controls the
feedback loop. It is the single public entry point. It maintains `sessionStore` across
iterations, appends feedback signals, enforces the iteration-5 escalation gate, and
assembles the final `AgentOutput`.

**Expected Outcomes**
- `conversation_agent/orchestrator.py` implements `WatsonxOrchestrator`
- `WatsonxOrchestrator.run(input: AgentInput) -> AgentOutput` — first-turn entry point
- `WatsonxOrchestrator.run_loop(input: AgentInput, feedback: str) -> AgentOutput` — loop re-entry
- Routing rules:
  - `menuSelection == "contact_support"` or `"get_human_help"` → `routeToHumanReview: True`, stop
  - Intent Agent returns `"clarify"` → return clarify response immediately, no loop
  - `iterationCount >= 5`: Content Agent receives signal to add escalation options
  - `confidence == "Low"` and `humanReviewOnLowConfidence` → set `routeToHumanReview: True`
    but keep loop options (user decides when to escalate)
- watsonx `ModelInference` client initialized once and passed to all agents
- Final output validated against `AgentOutput` Pydantic schema before returning

**Todo List**
1. Create `conversation_agent/orchestrator.py`
2. Implement `_load_env()` — load `.env` via `python-dotenv`; read
   `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`
3. Initialize watsonx client:
   ```python
   from ibm_watsonx_ai import Credentials
   from ibm_watsonx_ai.foundation_models import ModelInference
   credentials = Credentials(url=WATSONX_URL, api_key=WATSONX_API_KEY)
   model = ModelInference(model_id="ibm/granite-13b-chat-v2",
                          credentials=credentials,
                          project_id=WATSONX_PROJECT_ID)
   ```
4. Implement `run(input: AgentInput) -> AgentOutput`:
   a. If `menuSelection in ["contact_support", "get_human_help"]` → return `routeToHumanReview: True`
   b. Call `IntentAgent(model).run(input)` → `intent_result`
   c. If `intent_result["status"] == "clarify"` → build and return `clarify` AgentOutput
   d. If `intent_result["needRetrieval"]`:
      - Call `RetrievalAgent(model).run(intent_result, input)` → `retrieval_result`
      - Update `input.sessionStore.mcpSessionId`
   e. Else: `retrieval_result = {"results": [], "avgScore": 0.0, "lowConfidence": False, ...}`
   f. Call `ContentAgent(model).run(retrieval_result, intent_result, input)` → `content_result`
   g. If `confidence == "Low"` and `humanReviewOnLowConfidence`:
      set `routeToHumanReview = True` (loop options still present — user chooses)
   h. Assemble and validate `AgentOutput`; return
5. Implement `run_loop(input: AgentInput, feedback: str) -> AgentOutput`:
   - Called when user picks `"show_next"` or `"doesnt_help"`
   - Append `feedback` to `sessionStore.priorQueries`
   - Increment `sessionStore.iterationCount`
   - Re-call `run(input)` — agents see updated `iterationCount` and adapt
6. Create `conversation_agent/.env.example`:
   ```
   WATSONX_API_KEY=
   WATSONX_PROJECT_ID=
   WATSONX_URL=https://us-south.ml.cloud.ibm.com
   ```

**Relevant Context**
- `sessionStore` mutated in place — FAISS index, mcpSessionId, iterationCount,
  priorIntents, priorQueries all accumulate across iterations
- At `iterationCount == 5` the Content Agent automatically adds escalation options;
  orchestrator does not need to inject them separately
- watsonx `model` passed as constructor arg to all three agents

**Status** — `[ ] pending`

---

### Sub-Task 6 — Agent Prompt File (v1.0)

**Intent**
Save the canonical agent prompt / system spec as `agent_prompt.md` at the repo root,
tagged v1.0. This document serves as both human-readable design reference and a
machine-loadable system prompt for any LLM runtime.

**Expected Outcomes**
- `agent_prompt.md` exists at repo root
- YAML frontmatter: `name`, `version: v1.0`, `created`, `purpose`
- All five flow steps documented with sub-rules
- Loop mechanics section added (covering feedback signal, re-entry behavior per agent,
  no hard cap, escalation gate at iteration 5 via `"Contact support"` / `"Get human help"`)
- Empathetic option label design table included
- Multimedia section: images, video links, watsonx summary block
- Integration contract section: clarify re-invoke, loop re-invoke, human escalation

**Todo List**
1. Create `agent_prompt.md` at repo root
2. Write YAML frontmatter block
3. Sections to include:
   - Purpose
   - Input JSON Schema (annotated field descriptions, including `feedbackSignal`)
   - Top-level Flow Steps (Steps 1–5 from original brief)
   - Loop Mechanics (trigger, per-agent behavior, no cap, iteration-5 escalation gate)
   - Empathetic Option Label Design table
   - Multimedia in Content (images, video links, watsonx summary block)
   - Behavioral Constraints
   - Output JSON Schema (annotated)
   - Developer Notes for Integration
   - Example Invocation Scenarios (Test A, B, C patterns)
   - Integration Contract (clarify re-invoke, loop re-invoke, human escalation)

**Relevant Context**
- No secrets or keys in this file
- The `feedbackSignal` field is new — document it clearly

**Status** — `[ ] pending`

---

### Sub-Task 7 — Test Runner & Baseline Examples

**Intent**
Build the test runner that exercises Test A, B, and C through the full orchestrator
(including a simulated second loop iteration for Test A), saves real JSON outputs, and
provides hand-crafted baseline examples for comparison.

**Expected Outcomes**
- `test_runner.py` at repo root runs all test cases and saves outputs to `test_outputs/`
- Test A also runs a second iteration (simulates user picking `"Refine search"`)
- Outputs saved: `test_a_output.json`, `test_a_loop2_output.json`, `test_b_output.json`,
  `test_c_output.json`
- Baseline files: `baseline_test_a.json`, `baseline_test_b.json`, `baseline_test_c.json`
- Each output includes `_meta: {test_id, iteration, timestamp, mcp_called, indexSize}`
- Summary table printed to stdout

**Todo List**
1. Create `test_runner.py` at repo root
2. Define `TEST_CASES`:
   - **Test A** (iteration 1): `userInput="How do I configure OAuth 2.0 for Azure AD in Node.js?"`,
     `audience="developer"`, expected `steps + code_snippet`
   - **Test A** (iteration 2): same session, `feedbackSignal="refine_search"`,
     expected refined content with `> Iteration 2 result` marker
   - **Test B**: `userInput="How do I set up authentication?"`, `audience="developer"`,
     expected `responseType:"clarify"`
   - **Test C**: `userInput="Show me Contoso device reset policy"`, `audience="admin"`,
     expected retrieval; likely low confidence → `suggestedRefinements` + loop options
3. For each case: build `AgentInput`, call `WatsonxOrchestrator.run()` (or `run_loop()`),
   capture output, append `_meta`, save as pretty-printed JSON
4. Print summary table: `test_id | iteration | responseType | confidence | routeToHumanReview | indexSize`
5. Create `test_outputs/baseline_test_a.json` — hand-crafted expected output:
   - `responseType:"answer"`, `format:"steps"`, `confidence:"High"` or `"Medium"`,
     `sources` array with 1–3 entries, `interactiveOptions` always includes `refine_search`
     and `human_help`, `validationReport` with scores
6. Create `test_outputs/baseline_test_b.json` — hand-crafted expected output:
   - `responseType:"clarify"`, two `clarifyingQuestions`, three `suggestedActions`,
     `interactiveOptions` with quick-choice options
7. Create `test_outputs/baseline_test_c.json` — hand-crafted expected output:
   - `responseType:"low_confidence"` or `"answer"` with `confidence:"Low"`,
     `suggestedRefinements` array (2 items), `routeToHumanReview: true`,
     `interactiveOptions` includes both loop options

**Relevant Context**
- Loads `.env` before running via `python-dotenv`
- MCP session ID captured per test case and included in `_meta`
- Test A loop iteration reuses the same `sessionStore` object (FAISS index accumulates)

**Status** — `[ ] pending`

---

### Sub-Task 8 — Validation Script

**Intent**
Standalone post-hoc validator. Reads saved test output JSON files and checks schema
correctness, accessibility rules, loop option presence, and routing logic. Produces a
combined validation report.

**Expected Outcomes**
- `validation/validate_outputs.py` reads all `test_outputs/*.json` (excludes `baseline_*`)
- Produces `validation/validation_report.json` with pass/fail per check per test
- Checks include:
  - All required `AgentOutput` fields present and correct type
  - `interactiveOptions` always contains `show_next` and `doesnt_help` entries
  - `contact_support` and `get_human_help` present only when `_meta.iteration >= 5`
  - All `interactiveOptions` labels ≤ 40 chars
  - All images in `content` have non-empty alt text
  - `sources` non-empty when `responseType == "answer"`
  - `routeToHumanReview: true` when `confidence == "Low"` and `humanReviewOnLowConfidence` was true
  - `validationReport.accessibilityPass` matches actual content heuristics
  - Loop iteration outputs contain `> *Showing result set` marker in `content`
- Prints per-test summary table to stdout

**Todo List**
1. Create `validation/validate_outputs.py`
2. Implement `load_outputs(directory: str) -> list[dict]` — glob, skip `baseline_*`
3. Implement `validate_schema(output: dict) -> list[str]` — required fields + types
4. Implement `validate_loop_options(output: dict) -> list[str]`:
   - Check `show_next` and `doesnt_help` always present
   - Check `contact_support` / `get_human_help` present only when `_meta.iteration >= 5`
5. Implement `validate_accessibility(output: dict) -> list[str]` — headings, lists,
   no bare URLs, label length, all images have alt text in `content`
6. Implement `validate_routing(output: dict) -> list[str]` — `routeToHumanReview` logic
7. Implement `validate_loop_marker(output: dict) -> list[str]` — iteration 2+ outputs
   must contain iteration marker in `content`
8. Implement `run_all(outputs: list[dict]) -> dict` — aggregate into report
9. Write `validation/validation_report.json`
10. Print summary table to stdout

**Relevant Context**
- No orchestrator/agent imports — reads JSON only
- Runnable as `python validation/validate_outputs.py` with no arguments

**Status** — `[ ] pending`

---

## Final File Tree

```
conversation_agent/
  __init__.py
  schemas.py            ← AgentInput, AgentOutput, SessionStore, all nested models
  intent_agent.py       ← Agent 1: intent scoring, clarify, loop re-entry sharpening
  retrieval_agent.py    ← Agent 2: MCP + watsonx embed + FAISS + re-rank (RAG)
  content_agent.py      ← Agent 3: content synthesis + validationReport + loop options
  orchestrator.py       ← WatsonxOrchestrator: loop controller, assembles AgentOutput
  .env.example          ← WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL

test_outputs/
  .gitkeep
  baseline_test_a.json
  baseline_test_b.json
  baseline_test_c.json
  (test_a_output.json)         ← generated at runtime
  (test_a_loop2_output.json)   ← generated at runtime — loop iteration 2
  (test_b_output.json)
  (test_c_output.json)

validation/
  .gitkeep
  validate_outputs.py
  (validation_report.json)     ← generated at runtime

agent_prompt.md         ← canonical system prompt spec, tagged v1.0
test_runner.py          ← runs all test cases including loop iteration
```

---

## Key Constraints

- **PDF pipeline untouched** — no edits to existing files
- **Empathetic UX** — options always use friendly human language: `"Show me next"`, `"This doesn't help"`
- **Human escalation gate at iteration 5** — `"Contact support"` and `"Get human help"` appear
  only after 5 loop iterations; before that the user is never pressured to escalate
- **Hybrid labels** — fixed phrase (≤40 chars) + context-aware ARIA description with `{topic}`
- **Multimedia in content** — images (with alt text), video links from MCP sources,
  watsonx-generated plain-language summary block at top of every response
- **watsonx LLM used in Content Agent** — `ModelInference.generate_text()` for summary block;
  first real generative call in the pipeline
- **Loop has no hard cap** — user controls when to stop or escalate
- **RAG in Retrieval Agent** — watsonx embeddings + FAISS in-memory per session
- **Alternating MCP strictness** — odd iterations → 3, even → 2
- **FAISS index accumulates** — each loop adds new chunks; re-ranking improves over iterations
- **No secrets in code or prompt files** — all via env vars
- **Pydantic v2** — consistent with existing project
- **`requests` (sync)** for MCP HTTP calls
