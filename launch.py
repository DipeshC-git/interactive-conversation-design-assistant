"""
Launch the Conversation Design Assistant UI.

Starts the FastAPI server on port 8000 and opens the browser automatically.
Run with:
    python launch.py
OR from any directory:
    python "C:\\Users\\Dipesh-IdeaPad\\.bob\\playground\\launch.py"
"""
import os
import sys
import time
import subprocess
import webbrowser
import urllib.request
from pathlib import Path

# ── Resolve project root (the folder containing this file) ──────────────────
ROOT   = Path(__file__).resolve().parent
PYTHON = sys.executable
PORT   = 8000
URL    = f"http://localhost:{PORT}"

# ── Load .env ────────────────────────────────────────────────────────────────
env_path = ROOT / "conversation_agent" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

mock = os.environ.get("MOCK_MODE", "true").lower()
print(f"""
╔══════════════════════════════════════════════════════════════╗
║     Conversation Design Assistant                            ║
╠══════════════════════════════════════════════════════════════╣
║  Root      : {str(ROOT)[:52]}
║  Mode      : {"MOCK (no live API calls)" if mock == "true" else "LIVE (MS Learn MCP + watsonx.ai)"}
║  Server    : {URL}
║  Opening browser automatically...
╚══════════════════════════════════════════════════════════════╝
""")

# ── Start uvicorn — cwd MUST be project root so imports resolve ──────────────
proc = subprocess.Popen(
    [PYTHON, "-m", "uvicorn",
     "conversation_agent.api_server:app",
     "--host", "127.0.0.1",
     "--port", str(PORT),
     "--reload"],
    cwd=str(ROOT),                                   # <-- key fix
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)

# ── Wait up to 10 s for server to be ready ───────────────────────────────────
print("Waiting for server to start", end="", flush=True)
ready = False
for _ in range(20):
    try:
        urllib.request.urlopen(f"{URL}/health", timeout=1)
        ready = True
        break
    except Exception:
        print(".", end="", flush=True)
        time.sleep(0.5)
print()

if not ready:
    print(f"Server did not respond in time — check for errors above.")
    print(f"Try opening {URL} manually once the server is ready.")
else:
    print(f"Server is up!")

# ── Open browser ─────────────────────────────────────────────────────────────
webbrowser.open(URL)
print(f"Browser opened at {URL}")
print("Press Ctrl+C to stop the server.\n")

try:
    proc.wait()
except KeyboardInterrupt:
    print("\nShutting down...")
    proc.terminate()
