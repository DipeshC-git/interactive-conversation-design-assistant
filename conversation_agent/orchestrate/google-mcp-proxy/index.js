#!/usr/bin/env node
/**
 * google-mcp-proxy
 *
 * Local stdio MCP server that proxies all tool calls to the Google Developer
 * Knowledge MCP endpoint (https://developerknowledge.googleapis.com/mcp),
 * injecting the x-goog-api-key header automatically.
 *
 * Orchestrate registers this as a "local MCP server" with install command:
 *   node /absolute/path/to/google-mcp-proxy/index.js
 *
 * The API key is read from the GOOGLE_API_KEY environment variable, which
 * Orchestrate sets in the local MCP server's env configuration.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const GOOGLE_MCP_URL = "https://developerknowledge.googleapis.com/mcp";
const API_KEY = process.env.GOOGLE_API_KEY;

if (!API_KEY) {
  process.stderr.write("ERROR: GOOGLE_API_KEY environment variable is not set.\n");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// HTTP helper — sends a single JSON-RPC request to the Google MCP endpoint
// ---------------------------------------------------------------------------
async function googleRpc(method, params, sessionId) {
  const headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "x-goog-api-key": API_KEY,
  };
  if (sessionId) headers["mcp-session-id"] = sessionId;

  const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method, params: params ?? {} });
  const res = await fetch(GOOGLE_MCP_URL, { method: "POST", headers, body });
  const text = await res.text();

  // Google may return plain JSON or SSE (event: message\ndata: {...})
  // Try SSE first, fall back to plain JSON.
  const dataLine = text.split("\n").find(l => l.startsWith("data:"));
  if (dataLine) return JSON.parse(dataLine.slice("data:".length).trim());
  // Plain JSON
  const parsed = JSON.parse(text);
  if (parsed.error) throw new Error(JSON.stringify(parsed.error));
  return parsed;
}

// ---------------------------------------------------------------------------
// Discover tools from the Google MCP endpoint at startup
// ---------------------------------------------------------------------------
async function discoverTools() {
  const init = await googleRpc("initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "google-mcp-proxy", version: "1.0.0" },
  });

  const sessionId = init._sessionId ?? undefined; // stateless server, no session
  const listResp = await googleRpc("tools/list", {}, sessionId);
  return listResp.result?.tools ?? [];
}

// ---------------------------------------------------------------------------
// Build a Zod schema from an MCP JSON Schema object (handles top-level
// object schemas with simple string/array properties)
// ---------------------------------------------------------------------------
function buildZodSchema(inputSchema) {
  if (!inputSchema || inputSchema.type !== "object" || !inputSchema.properties) {
    return z.object({}).passthrough();
  }
  const shape = {};
  const required = new Set(inputSchema.required ?? []);
  for (const [key, prop] of Object.entries(inputSchema.properties)) {
    let field;
    if (prop.type === "array") {
      field = z.array(z.string()).describe(prop.description ?? key);
    } else {
      field = z.string().describe(prop.description ?? key);
    }
    if (!required.has(key)) field = field.optional();
    shape[key] = field;
  }
  return z.object(shape);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  // 1. Discover tools from Google MCP
  let tools;
  try {
    tools = await discoverTools();
  } catch (err) {
    process.stderr.write(`ERROR: Failed to discover tools from Google MCP: ${err.message}\n`);
    process.exit(1);
  }
  process.stderr.write(`google-mcp-proxy: discovered ${tools.length} tools: ${tools.map(t => t.name).join(", ")}\n`);

  // 2. Create local MCP server
  const server = new McpServer({ name: "google-developer-search", version: "1.0.0" });

  // 3. Register each discovered tool as a local proxy
  for (const tool of tools) {
    const toolName = tool.name;
    const schema = buildZodSchema(tool.inputSchema);

    server.tool(
      toolName,
      tool.description ?? toolName,
      schema.shape ?? {},
      async (args) => {
        try {
          const rpc = await googleRpc("tools/call", { name: toolName, arguments: args });
          if (rpc.error) {
            return {
              content: [{ type: "text", text: `Google MCP error: ${JSON.stringify(rpc.error)}` }],
              isError: true,
            };
          }
          // Forward the content array as-is
          const content = rpc.result?.content ?? [];
          if (content.length > 0) return { content };
          // Fallback: stringify the whole result
          return { content: [{ type: "text", text: JSON.stringify(rpc.result) }] };
        } catch (err) {
          return {
            content: [{ type: "text", text: `Proxy error: ${err.message}` }],
            isError: true,
          };
        }
      }
    );
  }

  // 4. Connect to stdio transport (Orchestrate spawns this process)
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("google-mcp-proxy: running on stdio\n");
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(1);
});
