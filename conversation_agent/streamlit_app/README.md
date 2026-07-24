# MS Learn Conversation Assistant — Streamlit Client

A lightweight local Streamlit web interface that connects to the **live watsonx Orchestrate** agent.
The LLM and agent logic run entirely in Orchestrate — this client is a pure frontend.

## Architecture

```
Browser (Streamlit UI)
  ↕  user messages / agent responses
orchestrate_client.py
  ↕  Watson Assistant v2 REST API
watsonx Orchestrate (live agent)
  ↕  MCP
microsoft_learn_search (MS Learn MCP Tool)
```

## Setup

1. **Install dependencies**

   ```bash
   cd conversation_agent/streamlit_app
   pip install -r requirements.txt
   ```

2. **Verify credentials in `conversation_agent/.env`**

   The following three variables must be set:

   | Variable | Description |
   |---|---|
   | `ORCHESTRATE_API_KEY` | ZenApiKey from your Orchestrate instance |
   | `ORCHESTRATE_INSTANCE_URL` | e.g. `https://api.us-south.assistant.watson.cloud.ibm.com` |
   | `ORCHESTRATE_AGENT_ID` | Assistant ID from Orchestrate > Deploy > API details |

   These are already populated in your `.env` — confirm they are current.

3. **Run**

   ```bash
   streamlit run app.py
   ```

   Opens at `http://localhost:8501` by default.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — chat history, Markdown rendering, choice buttons |
| `orchestrate_client.py` | API service layer — auth, session, message exchange |
| `requirements.txt` | Python dependencies |

## Features

- **Chat history** via `st.session_state.messages` — full conversation thread persists across reruns.
- **Rich Markdown rendering** — headings, lists, tables, fenced code blocks, and inline links all render properly.
- **Interactive choice extraction** — the agent's response tail is inspected for numbered lists, bullet points, and "Next Steps" / "Select an option" blocks.
- **Clickable choice buttons** — extracted choices render as `st.button` controls below the agent bubble; clicking one sends the exact choice string back to Orchestrate as the next user turn.
- **[See more: …] link handling** — the mandatory closing link is surfaced as a `st.link_button`, not mixed into the prose.
- **Sidebar topic starters** — five pre-loaded topic prompts let you start a conversation with one click.
- **Session management** — `Clear conversation` button deletes the Orchestrate session and resets state.
- **Error handling** — clear banners for missing credentials, expired tokens (401), wrong agent ID (404), and connection failures.

## Token expiry

If you get a `401 Unauthorized` error, your `ORCHESTRATE_API_KEY` (ZenApiKey) may have expired.  
Refresh it: Orchestrate UI → your user menu → Copy API key → paste into `.env`.
