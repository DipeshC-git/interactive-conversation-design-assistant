"""
Launch the Conversation Design Assistant UI.

Starts the FastAPI server on port 8000 and opens the browser automatically.
Run with:
    python launch.py
"""
import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

PYTHON = sys.executable
PORT   = 8000
URL    = f"http://localhost:{PORT}"

# Load .env so MOCK_MODE etc. are visible in this process too
env_path = Path(__file__).parent / "conversation_agent" / ".env"
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
║  Mode      : {"MOCK (no live API calls)" if mock == "true" else "LIVE (MS Learn MCP + watsonx.ai)"}{"" if mock != "true" else "          "}   ║
║  Server    : {URL}                          ║
║  Opening browser automatically…                              ║
╚══════════════════════════════════════════════════════════════╝
""")

# Start uvicorn as a subprocess
proc = subprocess.Popen(
    [PYTHON, "-m", "uvicorn",
     "conversation_agent.api_server:app",
     "--host", "0.0.0.0",
     "--port", str(PORT),
     "--reload"],
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)

# Wait for the server to be ready
import urllib.request, urllib.error
for _ in range(20):
    try:
        urllib.request.urlopen(f"{URL}/health", timeout=1)
        break
    except Exception:
        time.sleep(0.5)
else:
    print(f"Server may not be ready yet — opening {URL} anyway")

# Open browser
webbrowser.open(URL)
print(f"Browser opened at {URL}")
print("Press Ctrl+C to stop the server.\n")

try:
    proc.wait()
except KeyboardInterrupt:
    print("\nShutting down…")
    proc.terminate()
