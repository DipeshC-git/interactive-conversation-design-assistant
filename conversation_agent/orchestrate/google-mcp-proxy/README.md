# google-mcp-proxy

Vercel serverless proxy for the [Google Developer Knowledge MCP](https://developerknowledge.googleapis.com/mcp).

Injects `x-goog-api-key` automatically so watsonx Orchestrate can call the Google MCP endpoint without needing a custom header field in its UI.

## Deploy to Vercel (2 minutes)

### 1. Import the repo

1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import `DipeshC-git/interactive-conversation-design-assistant`
3. Set **Root Directory** to `conversation_agent/orchestrate/google-mcp-proxy`
4. Framework preset: **Other**
5. Click **Deploy**

### 2. Add environment variable

In Vercel → Project Settings → **Environment Variables**:

| Name | Value |
|---|---|
| `GOOGLE_API_KEY` | your key from `.env` |

Redeploy after adding the variable.

### 3. Note your proxy URL

After deploy, your proxy URL is:
```
https://<your-project-name>.vercel.app/api/mcp
```

### 4. Register in Orchestrate Agent Builder

**Add tool → MCP server → Remote**

| Field | Value |
|---|---|
| Server URL | `https://<your-project-name>.vercel.app/api/mcp` |
| Transport | Streamable HTTP |
| Custom headers | none needed |

The proxy injects `x-goog-api-key` on every request. Orchestrate sends no auth header.

## Local test

```bash
cd conversation_agent/orchestrate/google-mcp-proxy
npm install
GOOGLE_API_KEY=your_key node index.js
```
