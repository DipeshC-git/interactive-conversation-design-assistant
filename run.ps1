# run.ps1 — Start the Conversation Design Assistant
# Usage:  .\run.ps1
#         .\run.ps1 -Port 8080
#
# What this does:
#   1. Copies .env.example → conversation_agent/.env if .env is missing
#   2. Installs Python dependencies (fastapi, uvicorn, httpx, conversation-agent extras)
#   3. Starts uvicorn on http://localhost:<Port>
#   4. Opens the browser to the UI

param(
    [int]$Port = 8000
)

Set-Location $PSScriptRoot

# ── 1. Bootstrap .env ────────────────────────────────────────────────────────
$envFile = "conversation_agent\.env"
$envExample = "conversation_agent\.env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "[setup] Created conversation_agent\.env from .env.example" -ForegroundColor Cyan
        Write-Host "        Edit conversation_agent\.env to set credentials." -ForegroundColor Yellow
    } else {
        Write-Host "[warn]  .env.example not found — creating a minimal .env" -ForegroundColor Yellow
        "MOCK_MODE=true" | Set-Content $envFile
    }
}

# ── 2. Install dependencies ──────────────────────────────────────────────────
Write-Host "[deps] Installing Python dependencies…" -ForegroundColor Cyan
pip install --quiet fastapi "uvicorn[standard]" httpx pydantic requests numpy 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[warn] pip install had warnings — continuing." -ForegroundColor Yellow
}

# Optional: install conversation-agent extras (faiss, watsonx) if available
pip install --quiet -e ".[conversation-agent]" 2>&1 | Out-Null

# ── 3. Start server ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host " Conversation Design Assistant" -ForegroundColor White
Write-Host " http://localhost:$Port" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host ""
Write-Host " Endpoints:" -ForegroundColor White
Write-Host "   GET  /          → UI (ui/index.html)"
Write-Host "   POST /chat      → Python multi-agent pipeline"
Write-Host "   POST /loop      → Loop re-entry (show_next / doesnt_help)"
Write-Host "   POST /orchestrate/chat → watsonx Orchestrate proxy"
Write-Host "   GET  /health    → Mode flags"
Write-Host ""
Write-Host " Mode toggle appears in the UI header when ORCHESTRATE_INSTANCE_URL,"
Write-Host " ORCHESTRATE_API_KEY, and ORCHESTRATE_AGENT_ID are set in .env"
Write-Host ""
Write-Host " Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

# Open browser after a short delay
Start-Sleep -Milliseconds 1200
Start-Process "http://localhost:$Port"

# ── 4. Run uvicorn ───────────────────────────────────────────────────────────
python -m uvicorn conversation_agent.api_server:app --reload --port $Port
