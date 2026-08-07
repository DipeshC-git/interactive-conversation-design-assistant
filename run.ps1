# run.ps1 — Start Intently locally
# Usage:  .\run.ps1
#         .\run.ps1 -Port 8080
#         .\run.ps1 -Mock        (forces MOCK_MODE=true regardless of .env)
#
# What this does:
#   1. Copies .env.example → conversation_agent/.env if .env is missing
#   2. Installs Python dependencies
#   3. Starts uvicorn in the background
#   4. Waits until the server is healthy (up to 30 s)
#   5. Opens the browser

param(
    [int]$Port = 8000,
    [switch]$Mock
)

Set-Location $PSScriptRoot

# ── 1. Bootstrap .env ────────────────────────────────────────────────────────
$envFile    = "conversation_agent\.env"
$envExample = "conversation_agent\.env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "[setup] Created conversation_agent\.env from .env.example" -ForegroundColor Cyan
    } else {
        Write-Host "[setup] Creating minimal .env with MOCK_MODE=true" -ForegroundColor Yellow
        "MOCK_MODE=true" | Set-Content $envFile
    }
}

# Force mock mode if -Mock flag passed
if ($Mock) {
    $content = Get-Content $envFile -Raw
    $content  = $content -replace "(?m)^MOCK_MODE=.*$", "MOCK_MODE=true"
    Set-Content $envFile $content
    Write-Host "[setup] MOCK_MODE=true forced via -Mock flag" -ForegroundColor Yellow
}

# ── 2. Install dependencies ──────────────────────────────────────────────────
Write-Host "[deps]  Installing Python dependencies…" -ForegroundColor Cyan
python -m pip install --quiet --upgrade fastapi "uvicorn[standard]" httpx pydantic requests numpy 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[warn]  pip install had warnings — continuing." -ForegroundColor Yellow
}

# ── 3. Print banner ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host " Intently — Conversation Precision by Design" -ForegroundColor White
Write-Host " http://localhost:$Port" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host ""
Write-Host "  POST /chat              Python pipeline (mock or live)"
Write-Host "  POST /select            Layer 2 — content for selected intent"
Write-Host "  POST /orchestrate/chat  watsonx Orchestrate proxy"
Write-Host "  GET  /health            Mode flags"
Write-Host ""
Write-Host "  Credentials: conversation_agent\.env"
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

# ── 4. Start uvicorn in background ──────────────────────────────────────────
$job = Start-Job -ScriptBlock {
    param($port, $root)
    Set-Location $root
    python -m uvicorn conversation_agent.api_server:app --port $port 2>&1
} -ArgumentList $Port, $PSScriptRoot

Write-Host "[server] Starting uvicorn on port $Port (job $($job.Id))…" -ForegroundColor Cyan

# ── 5. Wait until /health responds (up to 30 s) ──────────────────────────────
$url     = "http://localhost:$Port/health"
$ready   = $false
$elapsed = 0
while (-not $ready -and $elapsed -lt 30) {
    Start-Sleep -Milliseconds 800
    $elapsed += 1
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true }
    } catch {}
    # Surface any startup errors from the job
    $out = Receive-Job -Job $job -Keep 2>&1
    if ($out -match "ERROR|Traceback|ModuleNotFoundError|ImportError") {
        Write-Host ""
        Write-Host "[ERROR] Server failed to start:" -ForegroundColor Red
        Write-Host $out -ForegroundColor Red
        Remove-Job -Job $job -Force
        exit 1
    }
}

if (-not $ready) {
    Write-Host "[warn]  Server did not respond within 30 s — opening browser anyway." -ForegroundColor Yellow
}

# ── 6. Open browser ──────────────────────────────────────────────────────────
Start-Process "http://localhost:$Port"
Write-Host "[ready] Browser opened → http://localhost:$Port" -ForegroundColor Green

# ── 7. Stream server output to console ──────────────────────────────────────
Write-Host ""
Write-Host "[logs]  Server output (Ctrl+C to stop):" -ForegroundColor DarkGray
try {
    while ($true) {
        $out = Receive-Job -Job $job 2>&1
        if ($out) { Write-Host $out }
        if ($job.State -ne 'Running') {
            Write-Host "[server] Process exited." -ForegroundColor Yellow
            break
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Stop-Job  -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
}
