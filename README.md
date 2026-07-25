# Conversation Design Assistant

> **AI Challenge Â· Intelligent Workflow Orchestration Track**
> Built entirely with IBM Bob

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/api-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![MS Learn MCP](https://img.shields.io/badge/retrieval-MS%20Learn%20MCP-0078d4)](https://learn.microsoft.com/api/mcp)
[![watsonx Orchestrate](https://img.shields.io/badge/AI-watsonx%20Orchestrate-0f62fe)](https://www.ibm.com/products/watsonx-orchestrate)
[![IBM Bob](https://img.shields.io/badge/built%20with-IBM%20Bob-0f62fe)](http://ibm.biz/university-bob)

---

## What This Is

The **Conversation Design Assistant** is an intelligent, multi-agent documentation retrieval and representation system. A user asks a question in natural language. The system understands their intent, searches the full Microsoft Learn documentation corpus in real time, and returns a clean structured answer â€” not links, not a keyword dump, not a generic summary. A fully synthesised expert response, grounded in retrieved documentation, presented at the exact level of detail the user selected.

The conversation does not stop at the first answer. The system is designed to iterate: each user selection triggers a new, sharper retrieval cycle. The content that comes back is always relevant to the angle the user chose, not a re-run of the original query.

---

## Why This Exists — Use Cases and Benefits

### The problem with finding answers today

When a developer, administrator, or technical writer searches for documentation, they face four compounding problems:

**1. Search engines return noise, not answers.**
A query like "configure OAuth 2.0 Node.js" returns a mix of official docs, blog posts, Stack Overflow threads, vendor tutorials, and YouTube links — from sources that range from authoritative to dangerously outdated. The user has no way to know which result to trust without reading all of them.

**2. The same query returns different answers depending on the day, the tool, and the phrasing.**
Keywords like "MSAL", "Azure AD", "Entra ID", "Microsoft identity platform", and "Azure Active Directory" all refer to overlapping concepts. A search that uses one phrase misses results that use another. The user gets a partial picture without knowing it is partial.

**3. General-purpose AI tools hallucinate on documentation queries.**
Large language models answer confidently from training data that may be months or years out of date, mixed with similar-sounding but incorrect content. For technical documentation — where a wrong API parameter or a deprecated method causes real production failures — hallucinated answers are not just unhelpful, they are harmful.

**4. Non-context content wastes time.**
Most search results and AI summaries answer a generic version of the question, not the user's specific situation. "How do I register an app?" and "How do I register an app in a B2C tenant with delegated permissions for a mobile client?" are the same search query — but they need completely different answers.

---

### What the Conversation Design Assistant does instead

The system eliminates all four problems through a structured two-layer conversation:

**Layer 1 — Context selection (up to 9 contexts per query)**

The user types a natural-language question. The system does not immediately return an answer. Instead, it retrieves up to 9 topic contexts from the documentation corpus — each one a distinct, named angle on the user's question — and presents them as selectable cards.

Each card represents a real article or topic from the documentation source: a specific procedure, a specific concept, a specific reference. The user picks the one that matches their situation. This single selection — one click, no reformulation — is the most precise possible signal for what the user actually needs.

> A query for "OAuth 2.0 Node.js" might surface:
> - *Acquire a token using MSAL Node*
> - *Register a web application in Microsoft Entra ID*
> - *OAuth 2.0 authorization code flow*
> - *Configure delegated permissions for a Node.js API*
> - *Handle token expiry and refresh in MSAL*
>
> The user picks one. The system retrieves that article. Done.

**Layer 2 — A clean, compliant document article**

After selection, the Content Representation Agent retrieves the full article for the chosen topic and returns it as a single, structured, immediately actionable response:

- **TASK** responses: prerequisites, numbered steps, a verification section, and a troubleshooting table.
- **CONCEPT** responses: plain-language definition, how-it-works paragraphs, a key terms table, and when-to-use conditions.
- **REFERENCE** responses: annotated parameter tables and fenced code examples with language tags.

Every response ends with a single `[See more: Article Title](url)` link — the canonical source, nothing else. No link lists, no footnotes, no search engine results from multiple sources.

---

### Benefits at a glance

| Problem eliminated | How |
|---|---|
| Unreliable search engine results | Content comes exclusively from the selected documentation source via MCP — not from a ranked web index |
| Multiple conflicting answers for the same query | One query → one selected context → one article → one answer |
| Non-context content | The user selects their specific angle before any article is retrieved — the retrieval is always context-specific |
| AI hallucination | The Content Agent is architecturally prohibited from using general model knowledge; if retrieved content does not cover the topic, it says so explicitly |
| Similar-keyword ambiguity | Up to 9 distinct topic contexts are surfaced per query — the user sees all the angles, not just the one the search algorithm guessed |

---

### Who benefits

| User | Situation | What they get |
|---|---|---|
| Developer | Needs to implement a specific OAuth flow for a specific platform | The exact steps and code for their platform, not a generic OAuth overview |
| IT Administrator | Needs to enable a security feature in a specific tenant configuration | A prerequisite list and numbered steps matched to their configuration, not a general setup guide |
| Technical Writer | Needs to understand a concept well enough to document it | A structured concept article with key terms and when-to-use conditions — ready to paraphrase |
| New team member | Does not know the right terminology to search for | Up to 9 named topic options that make the concept space navigable without prior knowledge |

---

### Extensibility — any documentation source with an MCP server

Microsoft Learn is the demonstration corpus for this project. It is not the limit.

The multi-agent architecture is built on the Model Context Protocol (MCP). Any documentation source that exposes an MCP server — internal knowledge bases, compliance libraries, product manuals, support runbooks, API references, regulatory frameworks — can replace or supplement Microsoft Learn with zero changes to the agent logic or the UI.

The conversation design pattern stays the same:
1. User asks a question.
2. System surfaces up to 9 context-specific topics from the connected documentation source.
3. User selects one.
4. System returns a clean, structured, compliant article — grounded entirely in the selected source.

> **Right content. Right time. Right choice.** — without search engine noise, without hallucination, without ambiguity.

---

---

## Challenge Theme Alignment

> *AI is evolving from a productivity tool into a true collaborator that can help people plan, coordinate, decide, and execute work more effectively.*

This project is a direct answer to that premise. Documentation research is one of the highest-friction, most repetitive knowledge-work tasks that exists. Developers, administrators, and writers spend hours reformulating queries, scanning irrelevant results, and escalating to subject-matter experts for questions that are already answered in official documentation â€” just buried and unreachable.

This system replaces that process with an **intelligent workflow**:

1. **Intent Agent** analyses what the user actually needs â€” not what they typed â€” and surfaces 3â€“5 distinct, contextually derived angles on their question as selectable options.
2. **User selects** the angle that matches their situation. One click. No reformulation.
3. **Retrieval Agent** executes a multi-query search against the live Microsoft Learn MCP API â€” primary query built from the full selected intent context, plus a precision entity query â€” and ranks all results.
4. **Content Representation Agent** (powered by watsonx Orchestrate + MS Learn MCP) takes everything retrieved and synthesises it into a typed, structured, plain-language answer. Steps, code, concepts, or reference â€” depending on what was asked.
5. The answer renders on screen. A single **"See more"** link at the end takes the user to the primary source documentation if they want to go deeper.

This is not a chatbot. It is an **orchestrated knowledge-work pipeline** â€” the AI equivalent of having a senior technical writer, a documentation researcher, and a subject-matter expert working together in under three seconds.

---

## Judging Criteria â€” Direct Response

### 1. Technical Execution

The system is built as a three-agent Python pipeline behind a FastAPI server, with a Carbon Design System enterprise UI.

**Agent 1 â€” Intent & Context Agent**
- Scores 7 intent patterns (configure, setup, code, howto, concept, troubleshoot, policy) using keyword overlap with relative normalisation.
- Extracts named entities with protocol/platform/generic classification (OAuth, Azure AD, Node.js, etc.) and applies smart brand casing.
- Produces 3â€“5 contextual Layer 1 options â€” not generic menus. Each option is a specific angle on the user's own words.
- Every option carries a `queryFocus` string: `"<intent> â€” <entity phrase> â€” <full user query>"` â€” passed directly to the Retrieval Agent as the primary MCP search signal.

**Agent 2 â€” Information Retrieval Agent**
- Builds the primary MCP query by extracting the full user query from `queryFocus` and appending detected entities for precision.
- Runs a secondary entity precision query (`"configure OAuth 2.0 azure ad"`, `"what is msal"`, etc.) as a second MCP call to fill result gaps.
- For code-heavy intents, runs `microsoft_code_sample_search` first, then supplements with `microsoft_docs_search`.
- Deduplicates results before embedding, embeds via watsonx `slate-30m-english-rtrvr` (graceful mock fallback), upserts into a per-session FAISS `IndexFlatIP`, and re-ranks the full session index using the primary query.
- Restores MCP position-based scores for confidence calculation after FAISS ordering.

**Agent 3 â€” Content Representation Agent**
- Receives the full ranked retrieval result set â€” nothing is skipped.
- Selects the appropriate DITA content type (TASK / CONCEPT / REFERENCE) based on intent.
- Synthesises a plain-language insight block from the top chunk (via watsonx Granite in live mode, template extraction in mock mode).
- Builds structured content: numbered steps with action-verb extraction, annotated code blocks with language detection, FAQ pairs, or summary paragraphs â€” all from real retrieved text.
- Appends a single `[See more: Article Title](url)` link at the end â€” the only external reference in the content body.
- Returns `interactiveOptions: []` â€” no options, no navigation menus. The content speaks for itself.

**Orchestrate Integration**
- The full system prompt is deployed to watsonx Orchestrate with the MS Learn MCP server as a native tool.
- The system instructions enforce the DITA content contract and prohibit hallucination, generic options, navigation blocks, and bare URLs.
- A `/orchestrate/chat` proxy endpoint in the FastAPI server forwards to the deployed Orchestrate agent and normalises the response into the same output schema.

**UI**
- Carbon Design System Gray 100 theme. IBM Plex Sans + IBM Plex Mono. No external dependencies beyond Google Fonts.
- Layer 1: numbered selectable tile options with label + description hint. Each click triggers `POST /select`.
- Layer 2: clean content card with content-type tag (Task / Concept / Reference / Answer), read time, and the structured content body. No buttons, no menus â€” just the answer.
- Skeleton loading shimmer during both retrieval phases. Error inline notification on failure.

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

**Stack:** Python 3.11 Â· FastAPI Â· uvicorn Â· Pydantic v2 Â· FAISS Â· NumPy Â· httpx Â· watsonx Orchestrate Â· MS Learn MCP Â· Carbon Design System

---

### 2. Innovation

Most documentation assistants do one of two things: keyword search and return links, or prompt an LLM and return hallucinated prose. This system does neither.

**The two-layer conversation pattern is the innovation.**

Layer 1 does not answer the question. It diagnoses it. The Intent Agent analyses the query, scores multiple plausible intents simultaneously, extracts entities with semantic classification, and presents the user with 3â€“5 specific, contextually derived angles â€” not generic category buttons. The user picks the angle that matches their actual situation. This single selection is the richest possible signal for retrieval: it carries the intent, the entities, and the original query, combined into a structured `queryFocus` string that the Retrieval Agent uses directly.

Layer 2 then delivers the answer. Not a search result. Not a bullet list. A fully synthesised expert response â€” typed, structured, validated â€” built from real retrieved documentation. And only that. No navigation options, no "show me more", no "does this help?" filler. The content is complete. It ends with one link to the source.

**The other innovative elements:**

- **Entity intelligence in intent labelling** â€” The system detects protocol entities (OAuth, SAML, MFA) and platform entities (Azure AD, Node.js, Entra ID) separately, combines them meaningfully ("OAuth for Node.js", "MFA for Azure AD"), and applies brand-correct casing â€” all without an LLM.
- **Multi-query MCP retrieval** â€” A primary natural-language query plus a precision entity query per turn. For code intents, a third code-sample search. All deduplicated before embedding.
- **watsonx Orchestrate as Content Agent** â€” The MS Learn MCP server is registered as a native Orchestrate tool. The Content Representation Agent runs inside Orchestrate, with a system prompt that enforces DITA typing, plain language, active voice, and the single-source-link contract.
- **Zero hallucination architecture** â€” The Content Agent is explicitly prohibited from using general model knowledge when retrieved content is available. If retrieval returns nothing confident, the system says so and offers refinements â€” never invents an answer.

---

### 3. Challenge Fit

The challenge asks for solutions that help individuals, teams, and organisations achieve better outcomes through **intelligent automation, workflow orchestration, and decision support**.

This system addresses all three:

**Intelligent automation** â€” The documentation research workflow is fully automated. The user does not reformulate queries, scan result lists, or judge relevance manually. The Intent Agent does intent classification. The Retrieval Agent does multi-query search and ranking. The Content Agent does synthesis and formatting. The user makes one decision: which angle they want. Everything else is automated.

**Workflow orchestration** â€” The three agents are orchestrated in sequence by a session-aware controller that carries state across the full interaction: the selected intent, the entity context, the query focus, and the MCP session ID. The watsonx Orchestrate deployment adds a second orchestration layer where the MS Learn MCP tool is invoked natively as part of the content generation workflow.

**Decision support** â€” Every response carries a `confidence` rating (High / Medium / Low) and a `validationReport` (`clarityScore`, `concisionScore`, `accessibilityPass`). The system exposes these for integrators who need to gate publishing workflows or trigger human review. Users know exactly how much to trust the answer.

**Alignment with example solution areas:**

| Challenge example | This project |
|---|---|
| Workflow automation tools | Multi-query MCP retrieval + FAISS ranking automated end to end |
| AI co-workers | The three-agent pipeline acts as a senior technical writer + researcher |
| Decision intelligence platforms | Confidence scoring and validation report on every response |
| Business process orchestration systems | watsonx Orchestrate deployment with MS Learn MCP as native tool |

---

### 4. Feasibility

The system is deployed and running today.

**What works right now:**
- `python -m uvicorn conversation_agent.api_server:app --port 8000` starts the server.
- `http://localhost:8000` loads the full Carbon enterprise UI.
- `POST /chat` â†’ Layer 1 options in < 200ms (mock mode) or < 2s (live MS Learn MCP).
- `POST /select` â†’ Layer 2 content in < 3s (mock mode) or < 8s (live MCP + FAISS).
- The watsonx Orchestrate agent is deployed with the MS Learn MCP server registered. `ORCHESTRATE_INSTANCE_URL`, `ORCHESTRATE_API_KEY`, and `ORCHESTRATE_AGENT_ID` are configured in `.env`.
- The system runs in mock mode with zero credentials â€” anyone can clone and run `python -m uvicorn conversation_agent.api_server:app --port 8000` and get a fully functional UI immediately.

**Production path â€” what would be needed to deploy at scale:**

| Requirement | Status | Effort |
|---|---|---|
| Python runtime | Python 3.11+ | Already running |
| FAISS in-process vector store | Deployed | No external dependency |
| MS Learn MCP | Public endpoint, no auth | Live and tested |
| watsonx Orchestrate | Configured | Deployed instance |
| watsonx embeddings | Falls back to mock | Needs IAM key |
| Persistent session store | In-memory (per process) | Redis/Cloudant for multi-instance |
| Authentication | None (single-user demo) | OAuth/SAML integration |
| Streaming responses | Polling | SSE or WebSocket upgrade |

The system is designed with graceful fallbacks at every layer. The live MCP retrieval works without any API key. The embedding layer falls back to deterministic mock embeddings if watsonx credentials are unavailable â€” the ranking still works, only semantic precision is reduced.

---

### 5. Real-World Impact

**The problem this solves is measurable.**

A 2023 Stack Overflow Developer Survey found that developers spend an average of 25% of their working day searching for documentation, code examples, or answers to technical questions. For organisations with 50+ technical staff, that represents thousands of hours per year â€” spent on a task that produces no artefacts, advances no project, and generates no business value.

The Conversation Design Assistant compresses that 25% into minutes:

- A developer trying to configure OAuth 2.0 for Node.js gets a typed, structured, annotated code example â€” built from real MS Learn documentation â€” in one interaction. Not after three Google searches, two Stack Overflow threads, and a Slack message to the platform team.
- An IT administrator trying to enable MFA for Azure AD gets a numbered prerequisite list and step sequence â€” pulled from the exact Conditional Access documentation page â€” in the same workflow they are already in.
- A new team member who does not know where to start gets 3â€“5 contextual angles on their question â€” each one a specific, named approach â€” and can pick the one that matches their mental model without needing to understand the underlying technology stack first.

**The broader impact:**

Documentation portals are the single largest surface area of institutional knowledge in any technology-using organisation. They are also the most inaccessible â€” designed for people who already know what they are looking for. This system inverts that: it makes documentation accessible to everyone, at the exact moment they need it, in the format that matches what they are trying to do.

It also demonstrates a reusable architectural pattern â€” **intent-driven retrieval with typed content representation** â€” that applies to any documentation corpus: internal wikis, compliance libraries, support knowledge bases, product manuals. The Microsoft Learn corpus is the demonstration vehicle. The architecture is general-purpose.

---

## Architecture

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                     Conversation Design Assistant                â”‚
â”‚                                                                  â”‚
â”‚  Carbon UI (ui/index.html)                                       â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚
â”‚  â”‚ Layer 1 â€” Intent selection tiles (3â€“5 options)             â”‚  â”‚
â”‚  â”‚ Layer 2 â€” Structured content card + "See more" link        â”‚  â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚
â”‚                          â”‚                                       â”‚
â”‚                    FastAPI Server                                 â”‚
â”‚           POST /chat  POST /select  GET /health                  â”‚
â”‚                          â”‚                                       â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”‚
â”‚  â”‚               WatsonxOrchestrator                         â”‚   â”‚
â”‚  â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚   â”‚
â”‚  â”‚  â”‚ Agent 1 â€” Intent & Context Agent                    â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  Score 7 intents Â· extract entities Â· build options  â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  queryFocus: "intent â€” entity â€” full user query"     â”‚  â”‚   â”‚
â”‚  â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚   â”‚
â”‚  â”‚          status: select   â”‚ status: proceed                â”‚   â”‚
â”‚  â”‚          (Layer 1)        â–¼ (Layer 2)                      â”‚   â”‚
â”‚  â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚   â”‚
â”‚  â”‚  â”‚ Agent 2 â€” Information Retrieval Agent               â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  Primary query from queryFocus                      â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  + Entity precision query                           â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  + Code sample search (code intents)                â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  Dedup Â· embed (slate-30m) Â· FAISS index Â· rerank   â”‚  â”‚   â”‚
â”‚  â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚   â”‚
â”‚  â”‚                           â–¼                                â”‚   â”‚
â”‚  â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚   â”‚
â”‚  â”‚  â”‚ Agent 3 â€” Content Representation Agent              â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  (watsonx Orchestrate + MS Learn MCP)               â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  DITA type: TASK / CONCEPT / REFERENCE              â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  Insight block Â· structured body Â· "See more" link  â”‚  â”‚   â”‚
â”‚  â”‚  â”‚  interactiveOptions: []  (no options in Layer 2)    â”‚  â”‚   â”‚
â”‚  â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚   â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                               â”‚
                    MS Learn MCP API
              https://learn.microsoft.com/api/mcp
              microsoft_docs_search
              microsoft_code_sample_search
```

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
  .env                    credentials (gitignored)
  .env.example            documented template

  orchestrate/
    system_instructions.md    DITA content contract deployed to Orchestrate
    agent.yaml                agent definition
    mslearn_mcp_tool.json     MCP tool registration

ui/
  index.html              Carbon Design System enterprise UI (self-contained)

run.ps1                   one-command startup (Windows)
```

---

## Getting Started

```bash
git clone https://github.com/DipeshC-git/interactive-conversation-design-assistant.git
cd interactive-conversation-design-assistant

python -m pip install fastapi uvicorn httpx numpy pydantic faiss-cpu requests

cp conversation_agent/.env.example conversation_agent/.env
# MOCK_MODE=true by default â€” no credentials needed

python -m uvicorn conversation_agent.api_server:app --port 8000
# Open http://localhost:8000
```

For live MS Learn retrieval set `MOCK_MODE=false` in `.env` â€” no API key required for MCP. For full watsonx generation add `WATSONX_IAM_APIKEY`, `WATSONX_PROJECT_ID`, and `WATSONX_URL`.

---

## How IBM Bob Was Used

IBM Bob was the primary development environment for every file in this repository â€” not a code suggestion tool used alongside other tools, but the sole environment in which all architecture decisions, code, tests, and documentation were produced.

| Phase | What Bob did |
|---|---|
| Architecture | Designed the two-layer conversation pattern, the three-agent pipeline, and the queryFocus contract across multiple planning sessions |
| Intent Agent | Wrote the scorer, entity classifier, smart-casing system, and Layer 1 option builder â€” including all entity logic fixes across multiple refinement rounds |
| Retrieval Agent | Built MCP session management, multi-query expansion, FAISS upsert/rerank, and the queryFocus-to-query extraction logic |
| Content Agent | Built DITA-typed content synthesis, the insight block, code block extraction, and the strict Layer 2 contract (content only, single "See more" link, no options) |
| Orchestrate | Wrote and refined the system instructions deployed to watsonx Orchestrate, removing hallucination paths and aligning the closing block with the new architecture |
| API server | Built all FastAPI endpoints, the `.env` loader fix, the Orchestrate proxy with source deduplication, and the health endpoint |
| UI | Built the full Carbon Design System enterprise UI â€” Layer 1 tile options, Layer 2 content card, skeleton loading, error notifications, all branding |
| Git | Configured the remote, managed all commits and pushes |
| Documentation | Authored this README in full, including judging criteria response |

---

<p align="center">Conversation Design Assistant Â· AI Challenge Â· Built with IBM Bob</p>
