# Intently — Proof of Concept

> **Status:** Validated · August 2025
> **Challenge:** IBM AI Builders Challenge — August Wildcard
> **Production URL:** https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud
> **Local URL:** http://localhost:8000

---

## 1. Problem Being Solved

Documentation retrieval is broken in three specific ways:

| Failure mode | What users experience |
|---|---|
| **Precision gap** | Users must already know the right search terms to find the right article. Most don't. |
| **Retrieval noise** | Search returns 10–50 results. Users spend time ranking and discarding, not acting. |
| **Hallucination risk** | AI chatbots answer from training knowledge, not from the current documentation source. Answers may be outdated, wrong, or fabricated. |

The root problem is structural: **the system asks users to express precise intent before they have enough context to do so.** This creates a loop — reformulate, search, scan, discard — that produces no artefacts and advances no work.

---

## 2. Hypothesis

> A two-layer conversation architecture — intent disambiguation first, typed content delivery second — can eliminate the precision gap, reduce noise to zero, and prevent hallucination at the architectural level.

This is tested against Microsoft Learn documentation as the corpus.

---

## 3. PoC Scope

### In scope

- Natural-language query submission (any technical topic covered by MS Learn)
- Layer 1: 3–5 intent-derived context selection tiles, grounded in the user's own words
- Layer 2: Single structured, typed, source-grounded response per selection
- Three content types: TASK (numbered steps), CONCEPT (plain-language explanation), REFERENCE (code with annotations)
- Confidence scoring (High / Medium / Low) on every response
- Validation report (clarityScore, concisionScore, accessibilityPass) on every response
- Mock mode for zero-credential local demonstration
- Live mode using MS Learn MCP (public endpoint) + watsonx Granite (IAM key)
- watsonx Orchestrate deploy path (embed UI via IBM Code Engine)

### Out of scope for PoC

- Multi-corpus retrieval (internal wikis, PDFs, Confluence)
- Persistent user accounts or cross-session memory
- Fine-tuned models
- Feedback loops / reinforcement from user ratings
- Mobile-native UI

---

## 4. Architecture Validation

### Two-layer conversation model

```
Turn 1 — POST /chat
  User submits natural-language query
  → IntentAgent scores 7 intent patterns, extracts named entities
  → Returns 3–5 contextual selection tiles (Layer 1)
  → Each tile carries a queryFocus: "intent — entity — full query"

Turn 2 — POST /select
  User selects a tile
  → RetrievalAgent builds MCP queries from queryFocus
  → Calls MS Learn MCP (microsoft_docs_search + microsoft_code_sample_search)
  → Deduplicates, embeds (slate-30m), upserts into per-session FAISS index, reranks
  → ContentAgent selects DITA type, synthesises response via watsonx Granite
  → Returns structured Layer 2 content card
```

### Agent boundaries validated

| Agent | Input | Output | Tested |
|---|---|---|---|
| IntentAgent | Raw user query string | Scored intents + entity list + Layer 1 options | ✓ Mock + Live |
| RetrievalAgent | queryFocus + intent + session store | Ranked chunk list + FAISS index | ✓ Mock + Live |
| ContentAgent | Ranked chunks + intent + audience | Typed markdown content + validation report | ✓ Mock + Live |

### FAISS in-process vector store

- Embedding dimension: 384 (slate-30m-english-rtrvr)
- Index type: `IndexFlatIP` (inner product, normalised vectors → cosine similarity)
- Chunks deduplicated by URL + text hash before upsert
- Index persisted in session store (bytes) across loop iterations
- No external vector database dependency — runs fully in-process

---

## 5. Test Cases Validated

Three baseline tests are committed in `test_outputs/`:

| Test | Query | Intent | Result |
|---|---|---|---|
| **A** | "How do I configure OAuth 2.0 for Node.js?" | configure_oauth | Layer 1: 5 options · Layer 2: TASK with code snippet |
| **B** | "Something about authentication maybe?" | setup_auth (low signal) | Layer 1: 5 options · Layer 2: CONCEPT, confidence Medium |
| **C** | "What is the device reset policy for Contoso?" | policy_lookup | Layer 1: 3 options · Layer 2: REFERENCE, confidence Low, human review flagged |

All three run end-to-end with `python test_runner.py`.

---

## 6. Deployment Validation

### Local (mock mode — zero credentials)

```bash
python launch.py           # starts server + opens browser
# OR
.\run.ps1 -Mock            # PowerShell, forces MOCK_MODE=true
```

### Local (live mode)

```bash
# Set in conversation_agent/.env:
MOCK_MODE=false
WATSONX_IAM_APIKEY=...
WATSONX_PROJECT_ID=...
WATSONX_URL=https://eu-de.ml.cloud.ibm.com
```

### IBM Code Engine (production)

The orchestrate embed server (`conversation_agent/orchestrate/`) is containerised and deployed to IBM Code Engine:

- **Production URL:** https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud
- **Region:** eu-de (Frankfurt)
- **Container:** Python 3.11-slim + Flask + gunicorn (2 workers)
- **Credentials:** injected as Code Engine environment variables (not baked into image)

```bash
# Build and push image
docker build -t icr.io/<namespace>/intently-orchestrate:latest ./conversation_agent/orchestrate
docker push icr.io/<namespace>/intently-orchestrate:latest

# Code Engine deploy (ibmcloud ce application update)
ibmcloud ce application update \
  --name intently-orchestrate \
  --image icr.io/<namespace>/intently-orchestrate:latest \
  --env HOST_URL=https://eu-de.watson-orchestrate.cloud.ibm.com \
  --env ORCHESTRATION_ID=... \
  --env ORCHESTRATE_AGENT_ID=... \
  --env AGENT_ENV_ID=... \
  --env ORCHESTRATE_API_KEY=...
```

---

## 7. Outcome

The PoC validates the hypothesis:

- **Precision gap eliminated:** Intent scoring + entity extraction surface contextually specific options from the user's own words. Users never need to reformulate.
- **Retrieval noise eliminated:** The user sees one structured answer, not a list of links. The FAISS rerank ensures the most relevant chunk drives the synthesis.
- **Hallucination prevented architecturally:** ContentAgent synthesises exclusively from retrieved MS Learn chunks. It does not call an LLM for general knowledge. The `[See more]` link is the only external reference — always the exact source document.
- **Confidence transparency:** Every response carries a confidence rating and a validation report. Low-confidence responses flag for human review rather than presenting uncertain content as fact.

The architecture is corpus-agnostic. Microsoft Learn is the PoC corpus. The same pipeline runs against any MCP-accessible documentation source without code changes.
