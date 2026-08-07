/**
 * Vercel Serverless Function — Google Developer Knowledge MCP Proxy
 *
 * Forwards all MCP requests to https://developerknowledge.googleapis.com/mcp
 * and injects the x-goog-api-key header automatically.
 *
 * Orchestrate registers this proxy as a Remote MCP server:
 *   URL: https://<your-vercel-app>.vercel.app/api/mcp
 *   Transport: Streamable HTTP
 *   No custom headers needed — key is injected here.
 *
 * GOOGLE_API_KEY is set as a Vercel Environment Variable (never in code).
 */

const UPSTREAM = "https://developerknowledge.googleapis.com/mcp";

export default async function handler(req, res) {
  // Only accept POST (MCP JSON-RPC)
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const apiKey = process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "GOOGLE_API_KEY not configured on proxy" });
    return;
  }

  // Forward headers from the incoming request, overriding/adding the key
  const forwardHeaders = {
    "Content-Type": req.headers["content-type"] || "application/json",
    "Accept":        req.headers["accept"]        || "application/json, text/event-stream",
    "x-goog-api-key": apiKey,
  };

  // Pass through MCP session ID if present
  if (req.headers["mcp-session-id"]) {
    forwardHeaders["mcp-session-id"] = req.headers["mcp-session-id"];
  }

  // Read the raw request body
  const body = await getRawBody(req);

  let upstreamRes;
  try {
    upstreamRes = await fetch(UPSTREAM, {
      method: "POST",
      headers: forwardHeaders,
      body,
    });
  } catch (err) {
    res.status(502).json({ error: `Upstream unreachable: ${err.message}` });
    return;
  }

  // Forward all response headers from Google back to Orchestrate
  const responseHeaders = {};
  for (const [key, value] of upstreamRes.headers.entries()) {
    // Skip headers that Vercel manages
    if (["content-encoding", "transfer-encoding", "connection"].includes(key.toLowerCase())) continue;
    responseHeaders[key] = value;
  }

  // Forward the session ID header specifically (MCP stateless server sends it back)
  const sessionId = upstreamRes.headers.get("mcp-session-id");
  if (sessionId) responseHeaders["mcp-session-id"] = sessionId;

  const responseBody = await upstreamRes.text();

  res.status(upstreamRes.status);
  for (const [k, v] of Object.entries(responseHeaders)) res.setHeader(k, v);
  res.send(responseBody);
}

/**
 * Read the full request body as a string.
 * Vercel provides req.body for JSON but we need the raw string to forward.
 */
function getRawBody(req) {
  return new Promise((resolve, reject) => {
    // If Vercel already parsed the body, re-stringify it
    if (req.body !== undefined) {
      resolve(typeof req.body === "string" ? req.body : JSON.stringify(req.body));
      return;
    }
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}
