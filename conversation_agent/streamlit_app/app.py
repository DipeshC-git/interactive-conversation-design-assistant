"""
app.py
──────
Streamlit frontend — MS Learn Product Knowledge Assistant.
Carbon Design System tokens · IBM favicon · product-consumer UX.

Run:
    cd conversation_agent/streamlit_app
    streamlit run app.py
"""

from __future__ import annotations

import re
import streamlit as st
from orchestrate_client import OrchestrateClient

# ─────────────────────────────────────────────────────────────────────────────
# Page config  (must be the very first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────

# IBM / watsonx SVG favicon encoded inline as a data URI
_IBM_FAVICON = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='4' fill='%230f62fe'/%3E"
    "%3Ctext x='50%25' y='50%25' dominant-baseline='central' text-anchor='middle' "
    "font-family='IBM Plex Sans,Arial,sans-serif' font-size='18' font-weight='700' "
    "fill='%23ffffff'%3Ew%3C/text%3E%3C/svg%3E"
)

st.set_page_config(
    page_title="Product Knowledge Assistant",
    page_icon=_IBM_FAVICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Carbon Design System CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    /* ── IBM Plex Sans via Google Fonts (system fallback if blocked) ── */
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

    /* ── Carbon tokens ── */
    :root {
        --cds-background:          #ffffff;
        --cds-layer-01:            #f4f4f4;
        --cds-layer-02:            #e8e8e8;
        --cds-border-subtle-00:    #e0e0e0;
        --cds-border-strong-01:    #8d8d8d;
        --cds-text-primary:        #161616;
        --cds-text-secondary:      #525252;
        --cds-text-placeholder:    #a8a8a8;
        --cds-interactive:         #0f62fe;
        --cds-interactive-hover:   #0353e9;
        --cds-support-success:     #24a148;
        --cds-support-error:       #da1e28;
        --cds-support-warning:     #f1c21b;
        --cds-tag-blue-background: #d0e2ff;
        --cds-tag-blue-color:      #0043ce;
        --cds-focus:               #0f62fe;
        --cds-spacing-02:  0.25rem;
        --cds-spacing-03:  0.5rem;
        --cds-spacing-04:  0.75rem;
        --cds-spacing-05:  1rem;
        --cds-spacing-06:  1.5rem;
        --cds-spacing-07:  2rem;
        --cds-productive-heading-01-size: 0.875rem;
        --cds-productive-heading-02-size: 1rem;
        --cds-productive-heading-03-size: 1.25rem;
        --cds-productive-heading-04-size: 1.75rem;
    }

    html, body, [class*="css"],
    .stMarkdown, .stChatMessage {
        font-family: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
        color: var(--cds-text-primary);
    }

    /* ── Hide Streamlit chrome ── */
    #MainMenu, footer, header { visibility: hidden; }

    /* ── Top header bar ── */
    .cds-shell-header {
        display: flex; align-items: center; gap: 12px;
        background: #161616;
        padding: 0 var(--cds-spacing-05);
        height: 48px;
        border-bottom: 1px solid #393939;
        margin-bottom: var(--cds-spacing-06);
    }
    .cds-shell-header .product-name {
        font-size: 14px; font-weight: 600; color: #f4f4f4;
        letter-spacing: 0.01em;
    }
    .cds-shell-header .product-name span {
        font-weight: 300; color: #c6c6c6;
    }
    .cds-shell-logo {
        display: flex; align-items: center; justify-content: center;
        width: 32px; height: 32px; border-radius: 4px;
        background: var(--cds-interactive);
        font-size: 14px; font-weight: 700; color: #fff;
        letter-spacing: -0.01em; flex-shrink: 0;
    }

    /* ── Page layout ── */
    .block-container { padding-top: 0 !important; max-width: 960px; }

    /* ── Section label ── */
    .cds-eyebrow {
        font-size: 11px; font-weight: 600; color: var(--cds-text-secondary);
        text-transform: uppercase; letter-spacing: 0.1em;
        margin-bottom: var(--cds-spacing-02);
    }

    /* ── Chat message bubbles ── */
    [data-testid="stChatMessage"] {
        border-radius: 0 !important;
        padding: var(--cds-spacing-04) 0 !important;
        background: transparent !important;
        border-bottom: 1px solid var(--cds-border-subtle-00);
    }
    [data-testid="stChatMessage"]:last-child {
        border-bottom: none;
    }

    /* ── Agent message markdown typography ── */
    [data-testid="stChatMessage"] .stMarkdown h1 { font-size: 1.25rem; font-weight: 600; margin: 12px 0 6px; }
    [data-testid="stChatMessage"] .stMarkdown h2 { font-size: 1.05rem; font-weight: 600; margin: 10px 0 4px; }
    [data-testid="stChatMessage"] .stMarkdown h3 { font-size: 0.95rem; font-weight: 600; margin: 8px 0 4px; }
    [data-testid="stChatMessage"] .stMarkdown p  { font-size: 0.875rem; line-height: 1.65; margin: 4px 0 8px; }
    [data-testid="stChatMessage"] .stMarkdown li { font-size: 0.875rem; line-height: 1.6; margin-bottom: 2px; }
    [data-testid="stChatMessage"] .stMarkdown code {
        font-family: 'IBM Plex Mono', 'Consolas', monospace;
        font-size: 0.8rem;
        background: var(--cds-layer-01);
        border: 1px solid var(--cds-border-subtle-00);
        border-radius: 2px; padding: 1px 5px;
        color: var(--cds-text-primary);
    }
    [data-testid="stChatMessage"] .stMarkdown pre code {
        display: block; padding: 12px 16px;
        overflow-x: auto; background: #1c1c1c; color: #f4f4f4;
        border: none; border-radius: 4px; font-size: 0.8rem;
    }
    [data-testid="stChatMessage"] .stMarkdown table {
        font-size: 0.8rem; border-collapse: collapse; width: 100%; margin: 8px 0;
    }
    [data-testid="stChatMessage"] .stMarkdown th {
        background: var(--cds-layer-01);
        border-bottom: 2px solid var(--cds-border-strong-01);
        padding: 6px 10px; text-align: left; font-weight: 600;
    }
    [data-testid="stChatMessage"] .stMarkdown td {
        padding: 5px 10px;
        border-bottom: 1px solid var(--cds-border-subtle-00);
    }

    /* ── Choice / action button strip ── */
    .choice-header {
        font-size: 11px; font-weight: 600; color: var(--cds-text-secondary);
        text-transform: uppercase; letter-spacing: 0.1em;
        margin: var(--cds-spacing-05) 0 var(--cds-spacing-03);
        padding-left: 10px;
        border-left: 3px solid var(--cds-interactive);
    }

    /* Make choice buttons look like Carbon ghost buttons */
    div[data-testid="stColumns"] > div > div > button,
    div[data-testid="column"] > div > div > button {
        background: transparent !important;
        border: 1px solid var(--cds-interactive) !important;
        border-radius: 0 !important;
        color: var(--cds-interactive) !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-size: 0.8125rem !important;
        font-weight: 400 !important;
        padding: 8px 14px !important;
        text-align: left !important;
        white-space: normal !important;
        height: auto !important;
        line-height: 1.45 !important;
        transition: background 80ms, color 80ms !important;
    }
    div[data-testid="stColumns"] > div > div > button:hover,
    div[data-testid="column"] > div > div > button:hover {
        background: var(--cds-tag-blue-background) !important;
        color: var(--cds-interactive-hover) !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: var(--cds-layer-01);
        border-right: 1px solid var(--cds-border-subtle-00);
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown li {
        font-size: 0.8125rem; color: var(--cds-text-secondary);
    }

    /* Sidebar topic starter buttons */
    [data-testid="stSidebar"] button {
        border-radius: 0 !important;
        font-size: 0.8125rem !important;
        text-align: left !important;
        width: 100% !important;
        margin-bottom: 2px !important;
        background: transparent !important;
        border: none !important;
        border-left: 3px solid transparent !important;
        color: var(--cds-text-primary) !important;
        padding: 7px 10px !important;
        white-space: normal !important;
        height: auto !important;
    }
    [data-testid="stSidebar"] button:hover {
        background: var(--cds-layer-02) !important;
        border-left: 3px solid var(--cds-interactive) !important;
    }

    /* ── Status pill ── */
    .cds-tag {
        display: inline-flex; align-items: center; gap: 5px;
        background: #defbe6; color: #044317;
        border: 1px solid #a7f0ba;
        border-radius: 12px;
        padding: 1px 10px;
        font-size: 11px; font-weight: 600;
    }
    .cds-tag-dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: var(--cds-support-success);
        display: inline-block;
    }
    .cds-tag-offline {
        background: var(--cds-layer-01); color: var(--cds-text-secondary);
        border-color: var(--cds-border-subtle-00);
    }

    .session-meta {
        font-size: 11px; color: var(--cds-text-secondary); margin-top: 3px;
    }

    /* ── Welcome card ── */
    .welcome-card {
        border: 1px solid var(--cds-border-subtle-00);
        background: var(--cds-layer-01);
        padding: var(--cds-spacing-06);
        margin: var(--cds-spacing-05) 0;
        border-left: 4px solid var(--cds-interactive);
    }
    .welcome-card h3 { margin: 0 0 6px; font-size: 1rem; font-weight: 600; }
    .welcome-card p  { margin: 0; font-size: 0.875rem; color: var(--cds-text-secondary); line-height: 1.6; }

    /* ── Error callout ── */
    .cds-callout-error {
        border: 1px solid var(--cds-support-error);
        border-left: 4px solid var(--cds-support-error);
        background: #fff1f1;
        padding: var(--cds-spacing-04) var(--cds-spacing-05);
        margin: var(--cds-spacing-04) 0;
        font-size: 0.8125rem;
    }
    .cds-callout-error strong { color: var(--cds-support-error); }
    .cds-callout-error pre {
        margin: 6px 0 0; font-size: 0.75rem;
        background: #ffd6d6; padding: 6px 8px;
        white-space: pre-wrap; word-break: break-word;
        font-family: 'IBM Plex Mono', monospace;
    }

    /* ── Chat input ── */
    .stChatInput textarea {
        border-radius: 0 !important;
        border: 1px solid var(--cds-border-strong-01) !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-size: 0.875rem !important;
    }
    .stChatInput textarea:focus {
        outline: 2px solid var(--cds-focus) !important;
        border-color: var(--cds-focus) !important;
    }

    /* ── Link button ── */
    a.cds-link {
        color: var(--cds-interactive);
        font-size: 0.8125rem;
        text-decoration: none;
        border-bottom: 1px solid var(--cds-tag-blue-background);
    }
    a.cds-link:hover { border-bottom-color: var(--cds-interactive); }

    /* ── Footer ── */
    .cds-footer {
        margin-top: var(--cds-spacing-07);
        padding-top: var(--cds-spacing-04);
        border-top: 1px solid var(--cds-border-subtle-00);
        font-size: 11px; color: var(--cds-text-secondary);
        display: flex; gap: 16px; flex-wrap: wrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Topic starters — product-knowledge consumer focused
# ─────────────────────────────────────────────────────────────────────────────

STARTER_TOPICS = [
    "What is OAuth 2.0 and how does it work?",
    "How do I register an app in Microsoft Entra ID?",
    "Show me MSAL token acquisition code in Python.",
    "What are the differences between Azure AD and Entra ID?",
    "How do I configure API permissions and grant admin consent?",
]

CAPABILITY_TAGS = [
    "Live MS Learn docs",
    "Structured answers",
    "Code samples",
    "Step-by-step guides",
    "Clickable follow-ups",
]

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "messages": [],
        "client": None,
        "session_active": False,
        "turn_count": 0,
        "error": "",
        "pending_input": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrate client bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def _get_client() -> OrchestrateClient:
    if st.session_state.client is None:
        st.session_state.client = OrchestrateClient()
    # create_session is a no-op shim for the native stateless API —
    # just sets session_active=True so the sidebar shows "Session active".
    if not st.session_state.session_active:
        st.session_state.client.create_session()
        st.session_state.session_active = True
    return st.session_state.client


# ─────────────────────────────────────────────────────────────────────────────
# Choice extraction
# ─────────────────────────────────────────────────────────────────────────────

_CHOICE_SECTION_RE = re.compile(
    r"(?:^|\n)"
    r"(?:#{1,4}\s*)??"
    r"(?:"
        r"what would you like"
        r"|next steps?"
        r"|select an option"
        r"|would you like to"
        r"|what.s next"
        r"|options?"
        r"|choose"
        r"|you can also"
        r"|continue with"
    r")[^\n]*\n"
    r"((?:(?:\d+\.|[-*•])\s+.+\n?)+)",
    re.IGNORECASE,
)

_TRAILING_LIST_RE = re.compile(r"(?:(?:\d+\.)\s+(.+))", re.MULTILINE)
_SEE_MORE_RE = re.compile(r"\[See more:\s*([^\]]+)\]\(([^)]+)\)\s*$", re.MULTILINE)


def extract_choices(response_text: str) -> list[str]:
    choices: list[str] = []

    for match in _CHOICE_SECTION_RE.finditer(response_text):
        block = match.group(1)
        for line in block.splitlines():
            cleaned = re.sub(r"^\s*(?:\d+\.|[-*•])\s+", "", line).strip()
            if cleaned:
                choices.append(cleaned)
        if choices:
            break

    if not choices:
        tail = response_text[-600:]
        for match in _TRAILING_LIST_RE.finditer(tail):
            item = match.group(1).strip()
            if item and not item.startswith("http"):
                choices.append(item)

    see_more = _SEE_MORE_RE.search(response_text)
    if see_more:
        title = see_more.group(1).strip()
        url = see_more.group(2).strip()
        choices.append(f"__SEEURL__{title}|{url}")

    return choices[:6]


def strip_see_more(response_text: str) -> str:
    return _SEE_MORE_RE.sub("", response_text).rstrip()


# ─────────────────────────────────────────────────────────────────────────────
# Send message
# ─────────────────────────────────────────────────────────────────────────────

def send_to_orchestrate(user_text: str) -> None:
    user_text = user_text.strip()
    if not user_text:
        return

    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.turn_count += 1
    st.session_state.error = ""

    try:
        client = _get_client()
        agent_text = client.send_message(user_text)
    except (RuntimeError, ConnectionError, EnvironmentError) as exc:
        st.session_state.error = str(exc)
        st.session_state.messages.pop()
        st.session_state.turn_count -= 1
        return

    st.session_state.messages.append({"role": "agent", "content": agent_text})


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        # Branding
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;padding:8px 0 16px">
              <div style="width:36px;height:36px;border-radius:4px;background:#0f62fe;
                          display:flex;align-items:center;justify-content:center;
                          font-size:16px;font-weight:700;color:#fff;flex-shrink:0;">w</div>
              <div>
                <div style="font-size:13px;font-weight:600;color:#161616;line-height:1.2">Product Knowledge</div>
                <div style="font-size:11px;color:#525252">MS Learn Assistant</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Session status
        if st.session_state.session_active:
            st.markdown(
                f'<span class="cds-tag"><span class="cds-tag-dot"></span>Session active</span>'
                f'<p class="session-meta">Turn {st.session_state.turn_count}</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="cds-tag cds-tag-offline">No session</span>'
                '<p class="session-meta">Send a message to start</p>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # Topic starters
        st.markdown('<p class="cds-eyebrow">Quick start</p>', unsafe_allow_html=True)
        for topic in STARTER_TOPICS:
            if st.button(topic, key=f"topic_{topic}", use_container_width=True):
                st.session_state.pending_input = topic

        st.markdown("---")

        # Capabilities
        st.markdown('<p class="cds-eyebrow">Capabilities</p>', unsafe_allow_html=True)
        for cap in CAPABILITY_TAGS:
            st.markdown(
                f'<span style="display:inline-block;background:#d0e2ff;color:#0043ce;'
                f'border-radius:10px;padding:2px 9px;font-size:11px;font-weight:500;'
                f'margin:2px 2px 2px 0">{cap}</span>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # Architecture note
        st.markdown(
            '<p class="cds-eyebrow">Powered by</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <ul style="font-size:12px;color:#525252;padding-left:16px;margin:4px 0">
            <li>watsonx Orchestrate (agent logic)</li>
            <li>MS Learn MCP Tool (live docs)</li>
            <li>DITA-structured output layer</li>
            </ul>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # Clear button
        if st.button("Clear conversation", use_container_width=True, type="secondary"):
            if st.session_state.client and st.session_state.session_active:
                st.session_state.client.delete_session()
            for k in ("messages", "client", "session_active", "turn_count", "error", "pending_input"):
                st.session_state[k] = [] if k == "messages" else (
                    None if k == "client" else
                    False if k == "session_active" else
                    0 if k == "turn_count" else ""
                )
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Chat rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_chat() -> None:
    messages = st.session_state.messages

    for idx, msg in enumerate(messages):
        is_last_agent = msg["role"] == "agent" and idx == len(messages) - 1

        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])

        else:
            with st.chat_message(
                "assistant",
                avatar="data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='4' fill='%230f62fe'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='central' text-anchor='middle' font-family='IBM Plex Sans,Arial,sans-serif' font-size='18' font-weight='700' fill='%23ffffff'%3Ew%3C/text%3E%3C/svg%3E",
            ):
                body = strip_see_more(msg["content"])
                st.markdown(body)

                see_more = _SEE_MORE_RE.search(msg["content"])
                if see_more:
                    title = see_more.group(1).strip()
                    url = see_more.group(2).strip()
                    st.markdown(
                        f'📖 <a class="cds-link" href="{url}" target="_blank" rel="noopener">See more: {title}</a>',
                        unsafe_allow_html=True,
                    )

                if is_last_agent:
                    render_choices(msg["content"], idx)


def render_choices(response_text: str, msg_idx: int) -> None:
    choices = extract_choices(response_text)
    if not choices:
        return

    url_choices = [c for c in choices if c.startswith("__SEEURL__")]
    text_choices = [c for c in choices if not c.startswith("__SEEURL__")]

    if text_choices:
        st.markdown(
            '<p class="choice-header">Continue exploring</p>',
            unsafe_allow_html=True,
        )
        cols_per_row = min(3, len(text_choices))
        rows = [
            text_choices[i : i + cols_per_row]
            for i in range(0, len(text_choices), cols_per_row)
        ]
        for row in rows:
            cols = st.columns(len(row))
            for col, choice_text in zip(cols, row):
                label = (choice_text[:65] + "…") if len(choice_text) > 65 else choice_text
                if col.button(label, key=f"choice_{msg_idx}_{choice_text[:40]}", use_container_width=True):
                    st.session_state.pending_input = choice_text

    for uc in url_choices:
        _, payload = uc.split("__SEEURL__", 1)
        title, url = payload.split("|", 1)
        st.link_button(f"📖 Read: {title}", url=url, use_container_width=False)


# ─────────────────────────────────────────────────────────────────────────────
# Error callout
# ─────────────────────────────────────────────────────────────────────────────

def render_error() -> None:
    if not st.session_state.error:
        return
    err = st.session_state.error

    # Check if the bearer token is expired — show targeted guidance
    import os as _os, base64 as _b64, json as _json, time as _time
    bt = _os.getenv("WATSONX_BEARER_TOKEN", "").strip()
    token_expired = False
    ago_min = 0
    if bt:
        tok = bt[7:] if bt.lower().startswith("bearer ") else bt
        try:
            payload = _json.loads(_b64.b64decode(tok.split(".")[1] + "=="))
            exp = float(payload.get("exp", 0))
            if exp < _time.time():
                token_expired = True
                ago_min = int((_time.time() - exp) / 60)
        except Exception:
            pass

    if token_expired:
        st.markdown(
            f'<div class="cds-callout-error">'
            f'<strong>Session token expired {ago_min} min ago</strong><br>'
            f'Your <code>WATSONX_BEARER_TOKEN</code> in <code>.env</code> needs to be refreshed.'
            f'<pre>'
            f'1. Open Watson Orchestrate in Chrome/Edge.\n'
            f'2. Press F12 &rarr; Network tab.\n'
            f'3. Send any message to your agent in the Orchestrate UI.\n'
            f'4. Click any /api/v1/ request &rarr; Headers &rarr; copy the Authorization value\n'
            f'   (everything after "Bearer ").\n'
            f'5. Paste into WATSONX_BEARER_TOKEN= in conversation_agent/.env.\n'
            f'6. Click "Clear conversation" in the sidebar to reconnect.'
            f'</pre>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        # Generic error display
        status_match = re.search(r"\[(\d+)\]", err)
        status = status_match.group(1) if status_match else "Error"
        lines = err.splitlines()
        headline = lines[0] if lines else err
        detail = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        html = f'<div class="cds-callout-error"><strong>API {status}</strong> — {headline}'
        if detail:
            html += f"<pre>{detail}</pre>"
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Input bar
# ─────────────────────────────────────────────────────────────────────────────

def render_input() -> None:
    if st.session_state.pending_input:
        queued = st.session_state.pending_input
        st.session_state.pending_input = ""
        send_to_orchestrate(queued)
        st.rerun()

    user_input = st.chat_input(
        placeholder="Ask anything about Microsoft technologies…",
        key="chat_input_box",
    )
    if user_input:
        send_to_orchestrate(user_input)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main layout
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    render_sidebar()

    # ── Shell header bar ──
    st.markdown(
        """
        <div class="cds-shell-header">
          <div class="cds-shell-logo">w</div>
          <div class="product-name">Product Knowledge Assistant <span>/ MS Learn</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_error()

    # ── Welcome state ──
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="welcome-card">
              <h3>Start learning about any Microsoft technology</h3>
              <p>
                I retrieve live documentation from Microsoft Learn and give you a structured,
                immediately actionable answer — with code samples, step-by-step guides, and
                clickable follow-up suggestions. Pick a topic from the sidebar or type below.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_chat()
    render_input()

    # ── Footer ──
    st.markdown(
        '<div class="cds-footer">'
        '<span>watsonx Orchestrate</span>'
        '<span>MS Learn MCP Tool</span>'
        '<span>DITA-structured output</span>'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
