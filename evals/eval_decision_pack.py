"""
eval_decision_pack.py

#> Tests: Goal primitive — does the output serve the user's purpose?

Evaluates the decision_pack output in pipeline_output_v3.json
against ground_truth_decision_pack.json.

Usage:
    python evals/eval_decision_pack.py pipeline_output_v3.json

Target: 5+/6 checks passing.
"""

import json
import sys


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def run_eval(pipeline_output_path, ground_truth_path="contracts/nexus_staylink/v2_v3/ground_truth_decision_pack.json"):
    pipeline = load_json(pipeline_output_path)
    ground_truth = load_json(ground_truth_path)

    dp = pipeline.get("decision_pack", {})
    if not dp:
        print("FATAL: 'decision_pack' key not found in pipeline output.")
        print("Check that decision_pack agent is wired as final node in graph.py")
        sys.exit(1)

    results = []

    # ------------------------------------------------------------------
    # CHECK 1: overall_recommendation == "ESCALATE"
    # ------------------------------------------------------------------
    expected = ground_truth["overall_recommendation"]
    actual = dp.get("overall_recommendation")
    passed = actual == expected
    results.append({
        "check": 1,
        "name": "overall_recommendation is ESCALATE",
        "passed": passed,
        "expected": expected,
        "actual": actual
    })

    # ------------------------------------------------------------------
    # CHECK 2: At least 2 critical issues present
    # Ground truth has 2 critical violations (C1 POL-001, C4 POL-001)
    # ------------------------------------------------------------------
    critical_issues = dp.get("critical_issues", [])
    actual_count = len(critical_issues)
    passed = actual_count >= 2
    results.append({
        "check": 2,
        "name": "critical_issues has at least 2 entries",
        "passed": passed,
        "expected": ">=2",
        "actual": actual_count
    })

    # ------------------------------------------------------------------
    # CHECK 3: required_sign_offs contains at least 3 REQUIRED functions
    # Legal, Finance, Product, Commercial all flagged in pipeline
    # ------------------------------------------------------------------
    sign_offs = dp.get("required_sign_offs", {})
    required_count = sum(1 for v in sign_offs.values() if v == "REQUIRED")
    passed = required_count >= 3
    results.append({
        "check": 3,
        "name": "required_sign_offs has at least 3 REQUIRED functions",
        "passed": passed,
        "expected": ">=3",
        "actual": required_count
    })

    # ------------------------------------------------------------------
    # CHECK 4: compound_risks contains CR1 (hard requirement)
    # CR2 is documented known variance — dependency agent may merge CR1+CR2
    # into a single larger compound risk. Absence of CR2 is not a failure.
    # ------------------------------------------------------------------
    compound_risks = dp.get("compound_risks", [])
    risk_ids = [r.get("risk_id") for r in compound_risks]
    cr1_present = "CR1" in risk_ids
    cr2_present = "CR2" in risk_ids
    passed = cr1_present
    note = ""
    if not cr2_present:
        note = " | CR2 not found — known variance, dependency agent may merge into CR1. Not a failure."
    results.append({
        "check": 4,
        "name": "compound_risks contains CR1 (CR2 known variance)",
        "passed": passed,
        "expected": "CR1 present (CR2 optional)",
        "actual": f"CR1={cr1_present}, CR2={cr2_present}, risk_ids found={risk_ids}{note}"
    })

    # ------------------------------------------------------------------
    # CHECK 5: escalation_items is non-empty
    # ------------------------------------------------------------------
    escalation_items = dp.get("escalation_items", [])
    passed = len(escalation_items) >= 1
    results.append({
        "check": 5,
        "name": "escalation_items is non-empty",
        "passed": passed,
        "expected": ">=1 item",
        "actual": len(escalation_items)
    })

    # ------------------------------------------------------------------
    # CHECK 6: review_progress is populated with correct total
    # Pipeline detected 6 changes (Gemini 2.5 Flash canonical output)
    # ------------------------------------------------------------------
    review_progress = dp.get("review_progress", {})
    total = review_progress.get("total_changes_detected")
    passed = total == 6
    results.append({
        "check": 6,
        "name": "review_progress.total_changes_detected == 6",
        "passed": passed,
        "expected": 6,
        "actual": total
    })

    # ------------------------------------------------------------------
    # PRINT RESULTS
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("EVAL: Decision Pack Agent")
    print("=" * 60)

    passed_count = 0
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed_count += 1
        print(f"\nCheck {r['check']}: {status} — {r['name']}")
        if not r["passed"]:
            print(f"  Expected : {r['expected']}")
            print(f"  Actual   : {r['actual']}")

    print("\n" + "=" * 60)
    print(f"SCORE: {passed_count}/{len(results)}")
    target = 5
    if passed_count >= target:
        print(f"RESULT: PASS (target {target}+/{len(results)})")
    else:
        print(f"RESULT: FAIL (target {target}+/{len(results)}) — {target - passed_count} more check(s) needed")
    print("=" * 60 + "\n")

    return passed_count, len(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evals/eval_decision_pack.py pipeline_output_v3.json")
        sys.exit(1)
    run_eval(sys.argv[1])
