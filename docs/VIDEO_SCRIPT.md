# Intently — Demo Video Script
### IBM AI Builders Challenge · August Wildcard · 3-Minute Submission

> **Total runtime target:** 2 min 45 sec – 3 min 00 sec
> **Pacing guide:** ~130 words per minute · script is ~385 words of spoken content
> **Tone:** Direct, confident, technical — no filler phrases

---

## SEGMENT 1 — THE PROBLEM (0:00 – 0:30)

**[Screen: blank search box, cursor blinking]**

> "Every developer, every IT admin, every new team member has been here.
> You have a task. You open documentation. You search.
> And immediately — the loop begins.
>
> Too many results. Wrong version. Outdated article. You reformulate.
> Search again. Filter. Scan. Discard.
>
> You're not doing your work. You're trying to figure out how to find your work.
>
> Standard search returns links. AI chatbots return answers — but they may be hallucinated.
> Neither solves the real problem:
>
> **You cannot express precise intent before you have context.
> And you cannot get context without a precise query.**
>
> That's the loop. Intently breaks it."

---

## SEGMENT 2 — THE DEMO: LAYER 1 (0:30 – 1:15)

**[Screen: Intently UI at http://localhost:8000 or the Code Engine production URL]**

> "This is Intently — Conversation Precision by Design.
>
> I'll type a query — a real one, the kind developers actually write:
> *'How do I configure OAuth 2.0 for Node.js?'*"

**[Type query. Hit submit. Layer 1 tiles appear.]**

> "Instead of a list of links — or an answer that might be wrong —
> Intently surfaces five specific angles on my own question.
> Each one is grounded in my words. Each one represents a different intent.
>
> Configure the OAuth 2.0 flow.
> Set up authentication for Node.js.
> Get a working code example.
> Understand the concept.
> Troubleshoot common errors.
>
> This is Layer 1 — context selection.
> The AI isn't answering yet. It's asking me: *which angle is your angle?*
>
> I'll select: *Get a Node.js code example.*"

---

## SEGMENT 3 — THE DEMO: LAYER 2 (1:15 – 2:00)

**[Screen: Layer 2 content card appears — code snippet, annotations, See more link]**

> "Layer 2 responds in under three seconds.
>
> Not a list of links. Not a summary of summaries.
> A single, structured, annotated code block — built entirely from real Microsoft Learn documentation.
> Every line retrieved. Every annotation grounded in the source.
>
> At the top: a plain-language insight — what this code does and why.
> Below: the annotated implementation, ready to copy.
> At the bottom: one link — *See more* — pointing to the exact MS Learn article.
>
> No hallucination. Architecturally impossible.
> The system synthesises only from what it retrieved.
> If it didn't retrieve it, it doesn't say it.
>
> And every response carries a confidence rating and a validation report —
> clarity score, concision score, accessibility pass.
> Low-confidence responses flag for human review instead of presenting uncertainty as fact."

---

## SEGMENT 4 — ARCHITECTURE & IBM STACK (2:00 – 2:30)

**[Screen: architecture diagram or split — code editor + watsonx Orchestrate UI]**

> "Under the hood: three agents, orchestrated in sequence.
>
> Agent 1 — Intent Agent: scores seven intent patterns, extracts named entities,
> builds those context tiles from your own query.
>
> Agent 2 — Retrieval Agent: calls the MS Learn MCP endpoint,
> deduplicates results, embeds them with IBM's slate-30m model,
> ranks them in a per-session FAISS index.
>
> Agent 3 — Content Agent: selects the right DITA content type —
> task, concept, or reference — and synthesises the response via watsonx Granite.
>
> The full system is deployed to IBM Code Engine in production.
> It also runs as a watsonx Orchestrate agent with MS Learn MCP as a native tool —
> built and deployed entirely using IBM Bob."

---

## SEGMENT 5 — IMPACT & CLOSE (2:30 – 3:00)

**[Screen: return to clean UI, maybe replay the two-turn interaction fast]**

> "A 2023 Stack Overflow survey found developers spend roughly 25% of their day
> searching documentation. For a team of fifty, that's thousands of hours a year
> producing no business value.
>
> Intently compresses that to a single two-turn conversation.
> One query. One selection. One answer. Done.
>
> The architecture is corpus-agnostic.
> MS Learn is the demonstration. The same pipeline runs on any documentation source —
> internal wikis, compliance libraries, support portals, product manuals.
>
> Precision is not a feature. It's the design.
>
> Intently — built with IBM Bob."

---

## PRODUCTION NOTES

| Segment | Duration | What to show |
|---|---|---|
| 1 — Problem | 0:30 | Blank search box → lots of results → reformulation loop (screen record or simple animation) |
| 2 — Layer 1 demo | 0:45 | Live Intently UI: type query → tiles appear → select one |
| 3 — Layer 2 demo | 0:45 | Content card: insight block + annotated code + confidence badge + See more link |
| 4 — Architecture | 0:30 | Architecture diagram from README or Bob chat showing agent pipeline + Orchestrate deploy |
| 5 — Impact & close | 0:30 | Clean UI replay (fast) → title card: *Intently — Conversation Precision by Design* |

**Recording checklist:**
- [ ] Use production URL `https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud` or `localhost:8000` (either works — live mode preferred)
- [ ] Query to use: `How do I configure OAuth 2.0 for Node.js?` (most visually complete Layer 2 response)
- [ ] Second query option: `What is Conditional Access in Azure AD?` (demonstrates CONCEPT type)
- [ ] Mic check: no background noise — script spoken at measured pace, not rushed
- [ ] No filler words ("um", "so", "basically") — this is a judged submission
- [ ] Captions recommended for accessibility

**Judging criteria coverage:**

| Criterion | Where covered in script |
|---|---|
| Technical Execution | Segment 4 — three agents, FAISS, slate-30m, Granite, Code Engine, Orchestrate, MCP |
| Innovation | Segment 1 & 2 — two-layer intent architecture; context selection before retrieval |
| Challenge Fit | Segment 4 & 5 — workflow automation, AI co-worker, decision support, IBM Bob |
| Feasibility | Segment 4 — live on Code Engine; mock mode for zero-credential demo |
| Real-World Impact | Segment 5 — Stack Overflow stat; corpus-agnostic architecture; 25% time saving |
