"""
Content Representation Agent (Agent 3)

Layer 2 contract:
  - Returns pure structured content only (steps / code / faq / summary).
  - A single "See more" link to the primary source is appended at the end.
  - interactiveOptions is always [] — options live in Layer 1 only.

MOCK_MODE=true  -- watsonx summary call is mocked with a template string.
MOCK_MODE=false -- calls watsonx ModelInference.generate_text().
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

from conversation_agent.schemas import AgentInput, ValidationReport

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

# ---------------------------------------------------------------------------
# Format selection
# ---------------------------------------------------------------------------

_INTENT_FORMAT_MAP: dict[str, str] = {
    "configure_oauth": "code_snippet",
    "code_request":    "code_snippet",
    "general_howto":   "steps",
    "troubleshoot":    "steps",
    "policy_lookup":   "summary",
    "concept_explain": "faq",
    "setup_auth":      "steps",
}


def _select_format(intent: str, preference: str | None) -> str:
    if preference:
        return preference
    return _INTENT_FORMAT_MAP.get(intent, "summary")


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def _determine_confidence(avg_score: float) -> str:
    if avg_score >= 0.7:
        return "High"
    if avg_score >= 0.45:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# Result selection
# ---------------------------------------------------------------------------

def _select_top_results(results: list[dict], avg_score: float) -> list[dict]:
    if avg_score >= 0.45:
        return results[:3]
    return []



# ---------------------------------------------------------------------------
# watsonx summary (mock + live)
# ---------------------------------------------------------------------------

def _mock_summary(selected: list[dict], intent: str, audience: str) -> str:
    """
    Generate a plain-text insight sentence from the top chunk.
    Strips JSON artifacts, code blocks, markdown, and URLs so only
    readable prose remains.
    """
    if not selected:
        return "Review the sources below for more information."
    top = selected[0]
    text = top.get("text", top.get("snippet", ""))

    # Remove fenced code blocks entirely
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Strip markdown tables (lines containing | separators)
    text = re.sub(r"\|[^\n]*\|", "", text)
    # Strip JSON objects / arrays
    text = re.sub(r"\{[^{}]{0,400}\}", "", text)
    text = re.sub(r"\[[^\[\]]{0,200}\]", "", text)
    # Strip markdown images and links
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Strip headings, bold, inline code, bare URLs
    text = re.sub(r"^#+\s+", "", text, flags=re.M)
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Take the first 1-2 meaningful sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]
    summary = " ".join(sentences[:2]) if sentences else text[:200]
    return summary[:300] if summary else "Review the sources below for more information."


def _live_summary(selected: list[dict], intent: str, audience: str, model: object) -> str:
    """
    Call watsonx ModelInference.generate_text() for a plain-language summary block.
    Falls back to mock template on any error so the pipeline never hard-fails.
    """
    combined = " ".join(c.get("text", "")[:300] for c in selected[:2])
    prompt = (
        f"Summarize the following in 2-3 plain-language sentences for a {audience}. "
        f"Be concise, use active voice, and focus on what the reader needs to do or know. "
        f"Do not add markdown formatting — plain sentences only.\n\n"
        f"{combined}"
    )
    try:
        result = model.generate_text(prompt=prompt, guardrails=False)  # type: ignore[union-attr]
        # generate_text returns a str directly
        text = result.strip() if isinstance(result, str) else str(result).strip()
        # Strip any residual JSON artifacts (e.g. {"generated_text": ...})
        if text.startswith("{") and "generated_text" in text:
            import json as _json
            text = _json.loads(text).get("generated_text", text).strip()
        return text if text else _mock_summary(selected, intent, audience)
    except Exception:
        return _mock_summary(selected, intent, audience)


def _call_watsonx_summary(selected: list[dict], intent: str, audience: str,
                          model: object) -> str:
    if MOCK_MODE or model is None:
        return _mock_summary(selected, intent, audience)
    return _live_summary(selected, intent, audience, model)


# ---------------------------------------------------------------------------
# Content synthesis
# Layer 2 contract: pure content body only.
# A single "See more" link to the primary source is appended at the end.
# No options, no media sections, no score lists embedded in the body.
# ---------------------------------------------------------------------------

def _primary_source_url(selected: list[dict]) -> tuple[str, str]:
    """Return (url, title) for the top source with a real link, or ('', '')."""
    for chunk in selected:
        links = chunk.get("links") or []
        for url in links:
            if url and url != "#":
                title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
                return url, title
    return "", ""


def _synthesize_content(
    selected: list[dict],
    intent_result: dict,
    input_obj: AgentInput,
    fmt: str,
    watsonx_summary: str,
) -> str:
    intent    = intent_result.get("chosenIntent", "")
    entities  = intent_result.get("entities", [])
    iteration = input_obj.sessionStore.iterationCount
    topic     = input_obj.userInput.strip().rstrip("?")

    parts: list[str] = []

    if iteration > 0:
        parts.append(f"> *Showing result set {iteration + 1} — refined for you*\n")

    # Plain-language insight from retrieved content
    parts.append(f"> **Insight:** {watsonx_summary}\n")

    # Structured content body — DITA type chosen by intent or format preference
    if fmt == "steps" or intent in ("setup_auth", "general_howto", "configure_oauth"):
        parts.append(_build_steps(selected, topic))
    elif fmt == "code_snippet" or intent == "code_request":
        parts.append(_build_code_snippet(selected, intent, entities))
    elif intent == "concept_explain":
        parts.append(_build_concept(selected, topic))
    elif intent == "troubleshoot":
        parts.append(_build_troubleshoot(selected, topic))
    elif fmt == "faq":
        parts.append(_build_faq(selected, topic))
    else:
        parts.append(_build_summary(selected, topic))

    # Single "See more" link at the very end — the only external reference
    url, title = _primary_source_url(selected)
    if url:
        parts.append(f"\n[See more: {title}]({url})")

    content = "\n\n".join(parts)

    if len(content) > input_obj.maxLength:
        content = content[: input_obj.maxLength - 40] + "\n\n> *[Content truncated — see more via the link above]*"

    return content


def _extract_code_blocks(text: str) -> list[str]:
    """Pull fenced code blocks out of MCP-returned markdown text."""
    import re as _re
    return _re.findall(r"```[\w]*\n[\s\S]*?```", text)


def _build_steps(selected: list[dict], topic: str) -> str:
    """
    Build a numbered steps section from MCP text.
    Extracts sentences that look like instructions (contain verbs like
    'open', 'click', 'run', 'set', 'add', 'configure', 'install', 'create').
    Falls back to raw sentences if no instruction-like sentences are found.
    """
    import re as _re
    ACTION_RE = _re.compile(
        r"\b(open|click|go to|navigate|select|set|add|configure|install|"
        r"create|register|copy|paste|run|execute|enter|type|enable|disable|"
        r"assign|grant|deploy|download|upload|save|apply|verify|check)\b",
        _re.I,
    )
    lines = [f"## Steps — {topic}", ""]
    step_num = 1
    for chunk in selected[:3]:
        raw = chunk.get("text", "")
        # Prefer sentences that contain action verbs
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", raw) if len(s.strip()) > 15]
        action_sents = [s for s in sentences if ACTION_RE.search(s)]
        pool = action_sents if action_sents else sentences
        for s in pool[:4]:
            s = s.rstrip(".")
            lines.append(f"{step_num}. {s}.")
            step_num += 1
        if step_num > 6:
            break

    if step_num == 1:
        lines.append("1. Open the documentation link in the Sources section below.")
        lines.append("2. Follow the on-screen instructions for your environment.")

    lines += [
        "",
        "**Prerequisites:** Access to the relevant portal and a registered application.",
        "**Estimated time:** 15–30 minutes.",
        "",
        "> **Troubleshooting tip:** If you receive a 401 Unauthorized error, verify "
        "that your redirect URI and client credentials match exactly what is registered.",
    ]
    return "\n".join(lines)


def _build_code_snippet(selected: list[dict], intent: str, entities: list[str]) -> str:
    """
    Build a code section.
    Priority:
      1. Pre-extracted code_blocks field (mock data).
      2. Fenced block found inside chunk text (live MCP).
      3. Synthesised minimal annotated example.
    """
    lines = ["## Code Example", ""]

    # 1 — pre-extracted code_blocks field (used in mock data)
    found_code = None
    for chunk in selected:
        pre = chunk.get("code_blocks") or []
        if pre:
            found_code = pre[0]
            break

    # 2 — look for a real fenced code block inside chunk text
    if not found_code:
        for chunk in selected:
            blocks = _extract_code_blocks(chunk.get("text", ""))
            if blocks:
                found_code = blocks[0]
                break

    if found_code:
        lines.append(found_code)
    else:
        # 2 — synthesise a minimal annotated example
        # Use top chunk text as inline context so it reflects the real answer
        ctx = ""
        if selected:
            ctx = selected[0].get("text", "")[:400]

        # Detect language from entities
        lang = "javascript"
        ent_str = " ".join(entities).lower()
        if "python" in ent_str:
            lang = "python"
        elif "typescript" in ent_str:
            lang = "typescript"

        if lang == "python":
            lines.append(
                f"```python\n"
                f"# Required packages: msal (pip install msal)\n"
                f"# Security: store secrets in environment variables.\n"
                f"import os, msal\n\n"
                f"# Context from MS Learn:\n"
                + "\n".join(f"# {l}" for l in ctx.split(". ")[:4] if l.strip())
                + f"\n\napp = msal.ConfidentialClientApplication(\n"
                f"    os.environ['CLIENT_ID'],\n"
                f"    authority='https://login.microsoftonline.com/' + os.environ['TENANT_ID'],\n"
                f"    client_credential=os.environ['CLIENT_SECRET'],\n"
                f")\nresult = app.acquire_token_for_client(scopes=['https://graph.microsoft.com/.default'])\nprint(result.get('access_token'))\n"
                f"```"
            )
        else:
            lines.append(
                f"```{lang}\n"
                f"// Required packages: @azure/msal-node (npm install @azure/msal-node)\n"
                f"// Security: store clientSecret in environment variables — never in source code.\n"
                + "\n".join(f"// {l}" for l in ctx.split(". ")[:4] if l.strip())
                + f"\n\nconst msal = require('@azure/msal-node');\n"
                f"const cca = new msal.ConfidentialClientApplication({{\n"
                f"  auth: {{\n"
                f"    clientId: process.env.CLIENT_ID,\n"
                f"    authority: 'https://login.microsoftonline.com/' + process.env.TENANT_ID,\n"
                f"    clientSecret: process.env.CLIENT_SECRET,\n"
                f"  }},\n"
                f"}});\n\n"
                f"async function getToken(authCode) {{\n"
                f"  const resp = await cca.acquireTokenByCode({{\n"
                f"    code: authCode, scopes: ['User.Read'],\n"
                f"    redirectUri: process.env.REDIRECT_URI,\n"
                f"  }});\n"
                f"  return resp.accessToken;\n"
                f"}}\n"
                f"```"
            )

    return "\n".join(lines)


def _build_concept(selected: list[dict], topic: str) -> str:
    """DITA CONCEPT type — what it is, how it works, key terms, when to use."""
    import re as _re
    short = " ".join(topic.split()[:6])
    lines = [f"## What is {short}?", ""]

    if selected:
        first = selected[0].get("text", "").strip()
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", first) if len(s.strip()) > 10]
        one_line = sentences[0] if sentences else first[:160]
        lines.append(f"> **In one sentence:** {one_line}")
        lines.append("")
        lines.append("### How it works")
        para_sents = sentences[1:5] if len(sentences) > 1 else sentences
        lines.append(" ".join(para_sents))
        lines.append("")

    if len(selected) > 1:
        lines.append("### Key terms")
        lines.append("| Term | Definition |")
        lines.append("|---|---|")
        for chunk in selected[1:3]:
            text = chunk.get("text", "").strip()
            sents = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10]
            # Use the snippet as the term name; first sentence as definition
            term  = chunk.get("snippet", "")[:60].split("—")[0].strip()
            defn  = sents[0][:120] if sents else text[:120]
            if term and defn:
                lines.append(f"| {term} | {defn} |")
        lines.append("")

    lines.append("### When to use it")
    lines.append("- When your application needs to verify the identity of a user.")
    lines.append("- When you need to delegate access to a protected resource without sharing credentials.")
    lines.append("- When integrating with Microsoft identity platform, Azure AD, or Entra ID.")

    return "\n".join(lines)


def _build_troubleshoot(selected: list[dict], topic: str) -> str:
    """DITA REFERENCE type — symptom/cause/fix troubleshooting table."""
    import re as _re
    lines = [f"## Troubleshoot — {topic}", ""]

    lines.append("### Symptom / Cause / Fix")
    lines.append("| Symptom | Likely cause | Fix |")
    lines.append("|---|---|---|")

    for chunk in selected[:3]:
        text = chunk.get("text", "").strip()
        snippet = chunk.get("snippet", "")
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15]
        if not sentences:
            continue
        # Extract symptom from snippet, cause + fix from text sentences
        symptom = snippet.split("—")[0].strip() if "—" in snippet else sentences[0][:80]
        cause   = sentences[1][:100] if len(sentences) > 1 else "See documentation."
        fix     = sentences[2][:100] if len(sentences) > 2 else sentences[-1][:100]
        symptom = symptom.rstrip(".")
        cause   = cause.rstrip(".")
        fix     = fix.rstrip(".")
        lines.append(f"| {symptom} | {cause} | {fix} |")

    lines.append("")
    lines.append("### General debugging steps")
    lines.append("1. Inspect the full error response body — the `error_description` field contains the AADSTS code.")
    lines.append("2. Verify your app registration: redirect URI, client ID, and tenant ID.")
    lines.append("3. Confirm required API permissions are added and admin consent granted.")
    lines.append("4. Check token expiry — access tokens expire after 60–90 minutes.")
    lines.append("5. Test the token using the [Microsoft JWT decoder](https://jwt.ms) to inspect claims.")

    return "\n".join(lines)


def _build_faq(selected: list[dict], topic: str) -> str:
    """
    Build an FAQ from the actual MCP content.
    Generates question/answer pairs from the real retrieved text.
    """
    import re as _re
    lines = [f"## FAQ — {topic}", ""]
    q_templates = [
        "What is {topic} and how does it work?",
        "When should I use {topic}?",
        "What are the key requirements for {topic}?",
    ]
    for i, chunk in enumerate(selected[:3]):
        text = chunk.get("text", "").strip()
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10]
        answer = " ".join(sentences[:2]) if sentences else text[:200]
        q = q_templates[i % len(q_templates)].format(topic=topic)
        lines.append(f"**{q}**")
        lines.append(f"{answer}")
        lines.append("")
    return "\n".join(lines)


def _build_summary(selected: list[dict], topic: str) -> str:
    """Build a summary from the actual MCP content — no inline source links."""
    import re as _re
    lines = [f"## Summary — {topic}", ""]
    for chunk in selected[:3]:
        text = chunk.get("text", "").strip()
        if not text:
            continue
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10]
        para = " ".join(sentences[:4])
        lines.append(para)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Low confidence response
# ---------------------------------------------------------------------------

def _low_confidence_response(refinements: list[str], topic: str) -> str:
    lines = [
        f"We couldn't find a confident answer about **{topic}** yet.",
        "",
        "Here are some refined search approaches that might help:",
        "",
    ]
    for r in refinements:
        lines.append(f"- {r}")
    return "\n".join(lines)


# _build_interactive_options removed — Layer 2 carries no interactive options.
# Options live exclusively in Layer 1 (interactiveOptions on responseType:"select").


# ---------------------------------------------------------------------------
# Read time + validation
# ---------------------------------------------------------------------------

def _estimate_read_time(text: str) -> str:
    words = len(text.split())
    minutes = max(1, math.ceil(words / 200))
    return f"{minutes} min read"


_PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+\w+ed\b", re.I
)
_BARE_URL_RE = re.compile(r"(?<!\()https?://\S+(?!\))", re.I)
_HEADING_RE = re.compile(r"^#{1,6}\s", re.M)
_LIST_RE = re.compile(r"^[-*\d]", re.M)


def _run_validation(content: str, fmt: str, max_length: int) -> ValidationReport:
    # Clarity score (0–5)
    sentences = [s.strip() for s in re.split(r"[.!?]", content) if len(s.strip()) > 5]
    avg_words = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
    clarity = 0
    if avg_words <= 20:
        clarity += 2
    if not _PASSIVE_RE.search(content):
        clarity += 2
    if _HEADING_RE.search(content):
        clarity += 1

    # Concision score (0–5)
    concision = 0
    if len(content) <= max_length:
        concision += 3
    if len(content) <= max_length * 0.8:
        concision += 2

    # Accessibility pass
    has_headings = bool(_HEADING_RE.search(content))
    has_lists = bool(_LIST_RE.search(content)) if fmt == "steps" else True
    no_bare_urls = not bool(_BARE_URL_RE.search(content))
    # Check all image alt texts (markdown images)
    images_have_alt = all(
        m.group(1).strip() != ""
        for m in re.finditer(r"!\[([^\]]*)\]", content)
    )
    accessibility_pass = has_headings and has_lists and no_bare_urls and images_have_alt

    return ValidationReport(
        clarityScore=clarity,
        concisionScore=concision,
        accessibilityPass=accessibility_pass,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class ContentAgent:
    """
    Agent 3 — Content Representation Agent.

    Layer 2 contract:
      - Returns pure structured content (steps / code / faq / summary).
      - A single "See more" link to the primary source URL is appended
        at the very end of the content body.
      - interactiveOptions is ALWAYS empty — options live in Layer 1 only.
      - sources[] is passed back for the UI to use if needed.
    """

    def __init__(self, model: object = None) -> None:
        self._model = model

    def run(
        self,
        retrieval_result: dict,
        intent_result: dict,
        input_obj: AgentInput,
    ) -> dict:
        iteration   = input_obj.sessionStore.iterationCount
        avg_score   = retrieval_result.get("avgScore", 0.0)
        results     = retrieval_result.get("results", [])
        refinements = retrieval_result.get("suggestedRefinements", [])

        confidence = _determine_confidence(avg_score)
        fmt        = _select_format(intent_result.get("chosenIntent", ""), input_obj.userFormatPreference)
        selected   = _select_top_results(results, avg_score)

        topic = input_obj.userInput.strip().rstrip("?")
        intent_result["_userInput"] = topic

        # Low confidence — no content to show; tell user to refine
        if not selected:
            short   = topic[:60] + ("…" if len(topic) > 60 else "")
            content = _low_confidence_response(refinements, short)
            return {
                "responseText": f"We couldn't find a confident answer for: \"{short}\". Try refining your search.",
                "format": fmt,
                "content": content,
                "interactiveOptions": [],   # no options in Layer 2
                "sources": [],
                "confidence": "Low",
                "suggestedRefinements": refinements,
                "estimatedReadTime": _estimate_read_time(content),
                "validationReport": _run_validation(content, fmt, input_obj.maxLength).model_dump(),
            }

        # Normal path — synthesise pure content
        watsonx_summary = _call_watsonx_summary(
            selected, intent_result.get("chosenIntent", ""), input_obj.audience, self._model
        )
        content = _synthesize_content(selected, intent_result, input_obj, fmt, watsonx_summary)

        short = topic[:60] + ("…" if len(topic) > 60 else "")
        response_text = (
            f"Refined result for: \"{short}\"." if iteration > 0
            else f"Here is what we found for: \"{short}\"."
        )

        sources = [
            {
                "file_path": r["file_path"],
                "page_numbers": r.get("page_numbers", ""),
                "score": r["score"],
                "url": (r.get("links") or [""])[0],
                "title": r["file_path"].rstrip("/").split("/")[-1]
                         .replace("-", " ").replace(".md", "").title(),
            }
            for r in selected
        ]

        return {
            "responseText": response_text,
            "format": fmt,
            "content": content,
            "interactiveOptions": [],       # Layer 2 carries no options
            "sources": sources,
            "confidence": confidence,
            "suggestedRefinements": refinements,
            "estimatedReadTime": _estimate_read_time(content),
            "validationReport": _run_validation(content, fmt, input_obj.maxLength).model_dump(),
        }
