"""
Validation Script — Conversation Design Assistant

Reads all test output JSON files from test_outputs/ (excludes baseline_*),
validates each against the schema and accessibility rules, writes
validation/validation_report.json, and prints a summary table.

Run: python validation/validate_outputs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

OUT_DIR = Path(__file__).parent.parent / "test_outputs"
REPORT_PATH = Path(__file__).parent / "validation_report.json"

REQUIRED_FIELDS = {
    "sessionId": str,
    "responseType": str,
    "responseText": str,
    "content": str,
    "interactiveOptions": list,
    "sources": list,
    "confidence": str,
    "routeToHumanReview": bool,
    "estimatedReadTime": str,
    "validationReport": dict,
}

VALID_RESPONSE_TYPES = {"answer", "clarify", "low_confidence"}
VALID_CONFIDENCE = {"High", "Medium", "Low"}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_outputs(directory: Path) -> list[dict]:
    outputs = []
    for f in sorted(directory.glob("*.json")):
        if f.name.startswith("baseline_"):
            continue
        outputs.append({
            "_filename": f.name,
            **json.loads(f.read_text(encoding="utf-8")),
        })
    return outputs


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_schema(output: dict) -> list[str]:
    errors = []
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in output:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(output[field], expected_type):
            errors.append(f"Field '{field}' expected {expected_type.__name__}, got {type(output[field]).__name__}")
    if output.get("responseType") not in VALID_RESPONSE_TYPES:
        errors.append(f"Invalid responseType: {output.get('responseType')}")
    if output.get("confidence") not in VALID_CONFIDENCE:
        errors.append(f"Invalid confidence: {output.get('confidence')}")
    vr = output.get("validationReport", {})
    for vf in ("clarityScore", "concisionScore", "accessibilityPass"):
        if vf not in vr:
            errors.append(f"validationReport missing field: {vf}")
    return errors


def validate_loop_options(output: dict) -> list[str]:
    errors = []
    options = output.get("interactiveOptions", [])
    ids = {o.get("id") for o in options}
    iteration = output.get("_meta", {}).get("iteration", 1)

    # clarify responses don't need loop options
    if output.get("responseType") == "clarify":
        return []

    if "show_next" not in ids:
        errors.append("Missing required option: 'show_next'")
    if "doesnt_help" not in ids:
        errors.append("Missing required option: 'doesnt_help'")

    if iteration >= 5:
        if "contact_support" not in ids:
            errors.append("Iteration >= 5 but 'contact_support' option missing")
        if "get_human_help" not in ids:
            errors.append("Iteration >= 5 but 'get_human_help' option missing")
    else:
        if "contact_support" in ids:
            errors.append("'contact_support' should not appear before iteration 5")
        if "get_human_help" in ids:
            errors.append("'get_human_help' should not appear before iteration 5")

    return errors


def validate_accessibility(output: dict) -> list[str]:
    errors = []
    content = output.get("content", "")
    fmt = output.get("format", "")
    options = output.get("interactiveOptions", [])

    # Label length
    for opt in options:
        label = opt.get("label", "")
        if len(label) > 40:
            errors.append(f"Option label exceeds 40 chars: '{label}' ({len(label)})")

    # No bare URLs in responseText
    import re
    bare_url = re.compile(r"(?<!\()https?://\S+(?!\))", re.I)
    if bare_url.search(output.get("responseText", "")):
        errors.append("responseText contains bare URL(s)")

    # For answer responses: check content has at least one heading
    if output.get("responseType") == "answer" and content:
        if not re.search(r"^#{1,6}\s", content, re.M):
            errors.append("answer content missing markdown headings")

    # Images must have non-empty alt text
    for m in re.finditer(r"!\[([^\]]*)\]", content):
        if not m.group(1).strip():
            errors.append("Image found with empty alt text in content")

    return errors


def validate_routing(output: dict) -> list[str]:
    errors = []
    confidence = output.get("confidence")
    route = output.get("routeToHumanReview", False)
    meta = output.get("_meta", {})

    if confidence == "Low" and not route:
        # Only flag if humanReviewOnLowConfidence was implicitly true
        # (clarify responses don't trigger human review)
        if output.get("responseType") != "clarify":
            errors.append("confidence=Low but routeToHumanReview=False (expected True)")

    return errors


def validate_loop_marker(output: dict) -> list[str]:
    errors = []
    iteration = output.get("_meta", {}).get("iteration", 1)
    content = output.get("content", "")
    if iteration >= 2 and output.get("responseType") == "answer":
        if "> *Showing result set" not in content:
            errors.append(f"Iteration {iteration} answer missing loop marker in content")
    return errors


def validate_sources(output: dict) -> list[str]:
    errors = []
    if output.get("responseType") == "answer":
        if not output.get("sources"):
            errors.append("responseType=answer but sources array is empty")
    return errors


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def run_all(outputs: list[dict]) -> dict:
    report = {"files_checked": len(outputs), "results": []}
    total_pass = total_fail = 0

    for output in outputs:
        fname = output.get("_filename", "unknown")
        checks = {
            "schema":         validate_schema(output),
            "loop_options":   validate_loop_options(output),
            "accessibility":  validate_accessibility(output),
            "routing":        validate_routing(output),
            "loop_marker":    validate_loop_marker(output),
            "sources":        validate_sources(output),
        }
        all_errors = [e for errs in checks.values() for e in errs]
        passed = len(all_errors) == 0
        if passed:
            total_pass += 1
        else:
            total_fail += 1

        report["results"].append({
            "file": fname,
            "passed": passed,
            "checks": {k: {"errors": v, "passed": len(v) == 0} for k, v in checks.items()},
        })

    report["summary"] = {
        "total": len(outputs),
        "passed": total_pass,
        "failed": total_fail,
    }
    return report


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    outputs = load_outputs(OUT_DIR)
    if not outputs:
        print("No test output files found in test_outputs/ (run test_runner.py first).")
        sys.exit(0)

    report = run_all(outputs)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary table
    print("\n" + "=" * 70)
    print(f"{'File':<30} {'Status':<8} {'Checks'}")
    print("-" * 70)
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        failed_checks = [k for k, v in r["checks"].items() if not v["passed"]]
        check_str = "all pass" if not failed_checks else ", ".join(failed_checks)
        print(f"{r['file']:<30} {status:<8} {check_str}")

    s = report["summary"]
    print("=" * 70)
    print(f"Total: {s['total']} | Passed: {s['passed']} | Failed: {s['failed']}")
    print(f"\nFull report: {REPORT_PATH}")

    # Print any errors for failed files
    for r in report["results"]:
        if not r["passed"]:
            print(f"\n--- {r['file']} ---")
            for check, result in r["checks"].items():
                for err in result["errors"]:
                    print(f"  [{check}] {err}")
