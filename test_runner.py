"""
Test Runner — Intently

Runs Test A (+ loop iteration), Test B, Test C through the full orchestrator.
Saves JSON outputs to test_outputs/. Prints a summary table.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Load env before imports
env_path = Path(__file__).parent / "conversation_agent" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from conversation_agent.orchestrator import WatsonxOrchestrator  # noqa: E402
from conversation_agent.schemas import AgentInput, SessionStore   # noqa: E402

OUT_DIR = Path("test_outputs")
OUT_DIR.mkdir(exist_ok=True)

orch = WatsonxOrchestrator()


def _save(filename: str, output_dict: dict) -> None:
    path = OUT_DIR / filename
    path.write_text(json.dumps(output_dict, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {path}")


def _meta(test_id: str, iteration: int, mcp_id: str | None, index_size: int) -> dict:
    return {
        "test_id": test_id,
        "iteration": iteration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mcp_called": mcp_id is not None,
        "mcpSessionId": mcp_id,
        "indexSize": index_size,
        "mock_mode": os.environ.get("MOCK_MODE", "true"),
    }


def _dump(output, test_id: str, iteration: int) -> dict:
    d = output.model_dump()
    store = getattr(output, "_session_store", None)
    d["_meta"] = _meta(
        test_id=test_id,
        iteration=iteration,
        mcp_id=output.mcpSessionId,
        index_size=len(store.faissChunks) if store else 0,
    )
    return d


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

results_summary: list[dict] = []

# ── Test A — iteration 1 ─────────────────────────────────────────────────
print("\n[Test A — iteration 1]")
inp_a = AgentInput(
    sessionId="test-a",
    userInput="How do I configure OAuth 2.0 for Azure AD in Node.js?",
    audience="developer",
    maxLength=2000,
)
out_a = orch.run(inp_a)
d_a = _dump(out_a, "A", 1)
d_a["_meta"]["indexSize"] = len(inp_a.sessionStore.faissChunks)
_save("test_a_output.json", d_a)
results_summary.append({
    "test_id": "A-1", "responseType": out_a.responseType,
    "confidence": out_a.confidence, "routeToHumanReview": out_a.routeToHumanReview,
    "indexSize": len(inp_a.sessionStore.faissChunks),
})

# ── Test A — iteration 2 (loop re-entry) ─────────────────────────────────
print("\n[Test A — iteration 2 (loop)]")
out_a2 = orch.run_loop(inp_a, "show_next")
d_a2 = _dump(out_a2, "A", 2)
d_a2["_meta"]["indexSize"] = len(inp_a.sessionStore.faissChunks)
_save("test_a_loop2_output.json", d_a2)
results_summary.append({
    "test_id": "A-2", "responseType": out_a2.responseType,
    "confidence": out_a2.confidence, "routeToHumanReview": out_a2.routeToHumanReview,
    "indexSize": len(inp_a.sessionStore.faissChunks),
})

# ── Test B ────────────────────────────────────────────────────────────────
print("\n[Test B — clarify]")
inp_b = AgentInput(
    sessionId="test-b",
    userInput="How do I set up authentication?",
    audience="developer",
)
out_b = orch.run(inp_b)
d_b = _dump(out_b, "B", 1)
_save("test_b_output.json", d_b)
results_summary.append({
    "test_id": "B", "responseType": out_b.responseType,
    "confidence": out_b.confidence, "routeToHumanReview": out_b.routeToHumanReview,
    "indexSize": 0,
})

# ── Test C ────────────────────────────────────────────────────────────────
print("\n[Test C — policy lookup]")
inp_c = AgentInput(
    sessionId="test-c",
    userInput="Show me Contoso device reset policy",
    audience="admin",
    humanReviewOnLowConfidence=True,
)
out_c = orch.run(inp_c)
d_c = _dump(out_c, "C", 1)
d_c["_meta"]["indexSize"] = len(inp_c.sessionStore.faissChunks)
_save("test_c_output.json", d_c)
results_summary.append({
    "test_id": "C", "responseType": out_c.responseType,
    "confidence": out_c.confidence, "routeToHumanReview": out_c.routeToHumanReview,
    "indexSize": len(inp_c.sessionStore.faissChunks),
})

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
print("\n" + "=" * 75)
print(f"{'Test':<8} {'responseType':<18} {'confidence':<10} {'HumanReview':<14} {'indexSize'}")
print("-" * 75)
for r in results_summary:
    print(
        f"{r['test_id']:<8} {r['responseType']:<18} {r['confidence']:<10} "
        f"{str(r['routeToHumanReview']):<14} {r['indexSize']}"
    )
print("=" * 75)
print("\nAll test outputs saved to test_outputs/")
