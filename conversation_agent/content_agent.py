"""
Content Representation Agent (Agent 3)

Synthesises original markdown content from retrieved chunks, injects a
watsonx-generated plain-language summary block, extracts multimedia
(images + video links) from MCP results, applies plain-language and
accessibility rules, builds empathetic interactive options that evolve
across loop iterations, and produces a validationReport.

MOCK_MODE=true  → watsonx summary call is mocked with a template string.
MOCK_MODE=false → calls watsonx ModelInference.generate_text().
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

import requests

from conversation_agent.schemas import AgentInput, InteractiveOption, ValidationReport

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
# Multimedia extraction
# ---------------------------------------------------------------------------

_IMAGE_RE = re.compile(r"https?://\S+\.(?:png|jpg|jpeg|gif|svg|webp)(?:\?\S*)?", re.I)
_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?(?:youtu\.be/|youtube\.com/embed/|learn\.microsoft\.com/\S+/video/)\S+",
    re.I,
)
_MSLEARN_RE = re.compile(r"https?://learn\.microsoft\.com/[^\s\"'>]+", re.I)


def _extract_multimedia(selected: list[dict]) -> dict:
    images: list[dict] = []
    videos: list[dict] = []
    seen_urls: set[str] = set()

    for chunk in selected:
        full_text = chunk.get("text", "") + " " + chunk.get("snippet", "")
        # Pull explicit image fields first
        for url in chunk.get("images", []):
            if url not in seen_urls:
                alt = f"Diagram from {chunk['file_path'].split('/')[-1].replace('.md','')}"
                images.append({"url": url, "alt": alt})
                seen_urls.add(url)
        # Regex scan for inline image URLs
        for url in _IMAGE_RE.findall(full_text):
            if url not in seen_urls:
                images.append({"url": url, "alt": "Reference diagram"})
                seen_urls.add(url)
        # Video links
        for url in chunk.get("links", []):
            if _VIDEO_RE.search(url) and url not in seen_urls:
                title = chunk["file_path"].split("/")[-1].replace(".md", "").replace("-", " ").title()
                videos.append({"url": url, "title": title})
                seen_urls.add(url)
        # MS Learn module links as "media"
        for url in _MSLEARN_RE.findall(full_text):
            if url not in seen_urls and url not in [v["url"] for v in videos]:
                title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
                videos.append({"url": url, "title": title})
                seen_urls.add(url)

    return {"images": images[:4], "videos": videos[:4]}  # cap at 4 each


# ---------------------------------------------------------------------------
# watsonx summary (mock + live)
# ---------------------------------------------------------------------------

def _mock_summary(selected: list[dict], intent: str, audience: str) -> str:
    """Template summary for mock mode — concise, plain-language."""
    if not selected:
        return "We searched our knowledge base but couldn't find a strong match for your query."
    top = selected[0]
    # Use snippet if available; otherwise take first 2 sentences of text
    raw = top.get("snippet", top.get("text", ""))
    # Strip any JSON artifacts from the text
    import re as _re
    raw = _re.sub(r'^\{"results":\[.*?"content":"', '', raw, flags=_re.S)
    raw = _re.sub(r'"\}.*$', '', raw, flags=_re.S)
    # Take first 150 clean chars
    clean = raw.replace('\n', ' ').strip()[:150]
    return (
        f"Here's what we found for {audience}s: {clean} "
        f"See the full details below."
    )


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
# ---------------------------------------------------------------------------

def _format_sources(selected: list[dict]) -> str:
    lines = ["## Sources", ""]
    for r in selected:
        link = (r.get('links') or ['#'])[0] or '#'
        lines.append(f"- [{r['file_path']}]({link}) — score: {r['score']:.2f}")
    return "\n".join(lines)


def _format_media(multimedia: dict) -> str:
    if not multimedia["images"] and not multimedia["videos"]:
        return ""
    lines = ["## Media", ""]
    for img in multimedia["images"]:
        lines.append(f"![{img['alt']}]({img['url']})")
    for vid in multimedia["videos"]:
        lines.append(f"▶ [{vid['title']}]({vid['url']})")
    return "\n".join(lines)


def _synthesize_content(
    selected: list[dict],
    intent_result: dict,
    input_obj: AgentInput,
    fmt: str,
    multimedia: dict,
    watsonx_summary: str,
) -> str:
    intent = intent_result.get("chosenIntent", "")
    entities = intent_result.get("entities", [])
    iteration = input_obj.sessionStore.iterationCount
    topic = ", ".join(entities[:2]) if entities else "your query"

    parts: list[str] = []

    # Iteration marker
    if iteration > 0:
        parts.append(f"> *Showing result set {iteration + 1} — refined for you*\n")

    # watsonx summary block
    parts.append(f"> **Insight:** {watsonx_summary}\n")

    # Main content by format
    if fmt == "steps":
        steps_text = _build_steps(selected, topic)
        parts.append(steps_text)

    elif fmt == "code_snippet":
        code_text = _build_code_snippet(selected, intent, entities)
        parts.append(code_text)

    elif fmt == "faq":
        faq_text = _build_faq(selected, topic)
        parts.append(faq_text)

    else:  # summary / table / default
        summary_text = _build_summary(selected, topic)
        parts.append(summary_text)

    # Media section
    media_md = _format_media(multimedia)
    if media_md:
        parts.append(media_md)

    # Sources
    if selected:
        parts.append(_format_sources(selected))

    content = "\n\n".join(parts)

    # Truncate to maxLength
    if len(content) > input_obj.maxLength:
        content = content[: input_obj.maxLength - 40] + "\n\n> *[See more…]*"

    return content


def _build_steps(selected: list[dict], topic: str) -> str:
    lines = [f"## Steps — {topic.title()}", ""]
    # Extract numbered steps from chunk text
    step_num = 1
    for chunk in selected[:2]:
        sentences = [s.strip() for s in chunk["text"].split(". ") if len(s.strip()) > 10]
        for s in sentences[:3]:
            lines.append(f"{step_num}. {s}.")
            step_num += 1
    if step_num == 1:
        lines.append("1. Review the documentation links in the Sources section below.")
    lines.append("")
    lines.append("**Prerequisites:** Access to the Azure portal and a registered app.")
    lines.append("**Estimated time:** 15–30 minutes.")
    lines.append("")
    lines.append(
        "> **Troubleshooting tip:** If you receive a 401 error, verify that the "
        "redirect URI in your app registration exactly matches the one in your code."
    )
    return "\n".join(lines)


def _build_code_snippet(selected: list[dict], intent: str, entities: list[str]) -> str:
    # Pick a pre-built minimal example based on intent
    if "oauth" in intent or "oauth" in " ".join(entities):
        code = (
            "```javascript\n"
            "// Required packages: @azure/msal-node (npm install @azure/msal-node)\n"
            "// Security: store clientSecret in environment variables — never in source code.\n"
            "const msal = require('@azure/msal-node');\n\n"
            "const config = {\n"
            "  auth: {\n"
            "    clientId: process.env.CLIENT_ID,       // App registration client ID\n"
            "    authority: 'https://login.microsoftonline.com/' + process.env.TENANT_ID,\n"
            "    clientSecret: process.env.CLIENT_SECRET,  // ⚠ Keep this secret\n"
            "  },\n"
            "};\n\n"
            "const cca = new msal.ConfidentialClientApplication(config);\n\n"
            "// Exchange auth code for access token\n"
            "async function getToken(authCode) {\n"
            "  const tokenRequest = {\n"
            "    code: authCode,\n"
            "    scopes: ['User.Read'],\n"
            "    redirectUri: process.env.REDIRECT_URI,\n"
            "  };\n"
            "  const response = await cca.acquireTokenByCode(tokenRequest);\n"
            "  return response.accessToken;\n"
            "}\n"
            "```"
        )
    else:
        # Generic snippet from top chunk
        top_text = selected[0]["text"][:200] if selected else "// See documentation."
        code = f"```\n// Example — adapt to your use case\n// {top_text}\n```"

    lines = ["## Code Example", "", code, ""]
    if selected:
        link = (selected[0].get("links") or ["#"])[0] or "#"
        lines.append(f"**Source:** [{selected[0]['file_path']}]({link})")
    return "\n".join(lines)


def _build_faq(selected: list[dict], topic: str) -> str:
    lines = [f"## FAQ — {topic.title()}", ""]
    for i, chunk in enumerate(selected[:3], 1):
        snippet = chunk.get("snippet", chunk["text"][:100])
        lines.append(f"**Q{i}: What does this cover?**")
        lines.append(f"A: {snippet}")
        lines.append("")
    return "\n".join(lines)


def _build_summary(selected: list[dict], topic: str) -> str:
    lines = [f"## Summary — {topic.title()}", ""]
    for chunk in selected[:2]:
        lines.append(chunk["text"][:300])
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


# ---------------------------------------------------------------------------
# Interactive options — empathetic, evolving with iteration
# ---------------------------------------------------------------------------

def _build_interactive_options(
    intent_result: dict,
    iteration: int,
) -> list[InteractiveOption]:
    entities = intent_result.get("entities", [])
    topic = ", ".join(entities[:2]) if entities else "this topic"

    options = [
        InteractiveOption(
            id="show_next",
            label="Show me next",
            description=f"See more results about {topic}",
        ),
        InteractiveOption(
            id="doesnt_help",
            label="This doesn't help",
            description=f"Tell us this missed the mark on {topic} and try a different angle",
        ),
    ]

    if iteration >= 5:
        options.extend([
            InteractiveOption(
                id="contact_support",
                label="Contact support",
                description=f"Connect with a specialist who can help you with {topic}",
            ),
            InteractiveOption(
                id="get_human_help",
                label="Get human help",
                description=f"Escalate to a human reviewer for personalized assistance with {topic}",
            ),
        ])

    return options


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
    """Agent 3 — Content synthesis, multimedia, empathetic UX, validation."""

    def __init__(self, model: object = None) -> None:
        self._model = model

    def run(
        self,
        retrieval_result: dict,
        intent_result: dict,
        input_obj: AgentInput,
    ) -> dict:
        iteration = input_obj.sessionStore.iterationCount
        avg_score = retrieval_result.get("avgScore", 0.0)
        results = retrieval_result.get("results", [])
        refinements = retrieval_result.get("suggestedRefinements", [])

        confidence = _determine_confidence(avg_score)
        fmt = _select_format(intent_result.get("chosenIntent", ""), input_obj.userFormatPreference)
        selected = _select_top_results(results, avg_score)

        entities = intent_result.get("entities", [])
        topic = ", ".join(entities[:2]) if entities else "your query"

        # Low confidence path
        if not selected:
            response_text = f"We're still looking for the best answer about {topic}. Try refining your search."
            content = _low_confidence_response(refinements, topic)
            validation = _run_validation(content, fmt, input_obj.maxLength)
            options = _build_interactive_options(intent_result, iteration)
            return {
                "responseText": response_text,
                "format": fmt,
                "content": content,
                "interactiveOptions": [o.model_dump() for o in options],
                "sources": [],
                "confidence": "Low",
                "suggestedRefinements": refinements,
                "estimatedReadTime": _estimate_read_time(content),
                "validationReport": validation.model_dump(),
            }

        # Normal path
        watsonx_summary = _call_watsonx_summary(
            selected, intent_result.get("chosenIntent", ""), input_obj.audience, self._model
        )
        multimedia = _extract_multimedia(selected)
        content = _synthesize_content(selected, intent_result, input_obj, fmt, multimedia, watsonx_summary)
        response_text = f"Here's what we found about {topic}."
        if iteration > 0:
            response_text = f"Here's a refined result for {topic} — hope this is closer to what you need."

        validation = _run_validation(content, fmt, input_obj.maxLength)
        options = _build_interactive_options(intent_result, iteration)
        sources = [
            {"file_path": r["file_path"], "page_numbers": r.get("page_numbers", ""), "score": r["score"]}
            for r in selected
        ]

        return {
            "responseText": response_text,
            "format": fmt,
            "content": content,
            "interactiveOptions": [o.model_dump() for o in options],
            "sources": sources,
            "confidence": confidence,
            "suggestedRefinements": refinements,
            "estimatedReadTime": _estimate_read_time(content),
            "validationReport": validation.model_dump(),
        }
