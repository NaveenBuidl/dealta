# evals/eval_stateful.py

#> Tests: State primitive — does version-aware state work?
#
# Evaluates Level 5: stateful v2->v3 tracking.
#
# What this checks:
#   1. Clause 4 (commission mechanism shift) detected — the invalidating change
#   2. Clause 5 (API suspension right) detected — compound risk participant
#   3. Clause 10 (indemnification carve-out) detected — routing only, no policy rule
#   4. Clause 9 (liability cap asymmetry) detected — compound risk amplifier
#   5. Finance sign-off marked invalidated
#   6. Invalidation correctly attributed to Clause 4 change
#   7. Clause 5 does NOT trigger invalidation (true negative)
#   8. Clause 9 does NOT trigger invalidation (true negative)
#
# Done criterion: this eval passes = Level 5 is complete.

import json
import sys
import os


def load_pipeline_output(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def evaluate(state: dict) -> dict:
    results = []

    detected = state.get("detected_changes", [])
    sign_offs = state.get("sign_offs", [])

    clause_nums_detected = {c["clause_number"] for c in detected}

    # --- Check 1: Clause 4 change detected ---
    clause4_found = 4 in clause_nums_detected
    results.append({
        "check": "Clause 4 (commission mechanism shift) detected",
        "passed": clause4_found,
        "note": "OK" if clause4_found else "Clause 4 change not found in detected_changes"
    })

    # --- Check 2: Clause 5 change detected ---
    clause5_found = 5 in clause_nums_detected
    results.append({
        "check": "Clause 5 (API suspension right) detected",
        "passed": clause5_found,
        "note": "OK" if clause5_found else "Clause 5 change not found in detected_changes"
    })

    # --- Check 3: Clause 10 change detected ---
    clause10_found = 10 in clause_nums_detected
    results.append({
        "check": "Clause 10 (indemnification carve-out) detected",
        "passed": clause10_found,
        "note": "OK" if clause10_found else "Clause 10 change not found in detected_changes"
    })

    # --- Check 4: Clause 9 change detected ---
    clause9_found = 9 in clause_nums_detected
    results.append({
        "check": "Clause 9 (liability cap asymmetry) detected",
        "passed": clause9_found,
        "note": "OK" if clause9_found else "Clause 9 change not found in detected_changes"
    })

    # --- Check 5: Finance sign-off exists and is invalidated ---
    finance_signoffs = [s for s in sign_offs if s.get("function") == "Finance"]
    invalidated_finance = [s for s in finance_signoffs if s.get("invalidated") is True]

    finance_invalidated = len(invalidated_finance) > 0
    results.append({
        "check": "Finance sign-off marked invalidated",
        "passed": finance_invalidated,
        "note": "OK" if finance_invalidated else (
            "No Finance sign-off found" if not finance_signoffs
            else "Finance sign-off exists but invalidated is not True"
        )
    })

    # --- Check 6: invalidated_by_change_id points to Clause 4 change ---
    correct_cause = False
    if invalidated_finance:
        clause4_changes = [c for c in detected if c["clause_number"] == 4]
        clause4_ids = {c["change_id"] for c in clause4_changes}

        for sf in invalidated_finance:
            if sf.get("invalidated_by_change_id") in clause4_ids:
                correct_cause = True
                break

    results.append({
        "check": "Invalidation correctly attributed to Clause 4 change",
        "passed": correct_cause,
        "note": "OK" if correct_cause else (
            "invalidated_by_change_id does not point to a Clause 4 change"
            if invalidated_finance else "No invalidated Finance sign-off to check"
        )
    })

    # --- Check 7: Clause 5 does NOT trigger invalidation (true negative) ---
    clause5_changes = [c for c in detected if c["clause_number"] == 5]
    clause5_ids = {c["change_id"] for c in clause5_changes}

    clause5_false_invalidation = any(
        s.get("invalidated_by_change_id") in clause5_ids
        for s in sign_offs
    )
    results.append({
        "check": "Clause 5 does NOT trigger invalidation (true negative)",
        "passed": not clause5_false_invalidation,
        "note": "OK" if not clause5_false_invalidation else "Clause 5 incorrectly caused an invalidation"
    })

    # --- Check 8: Clause 9 does NOT trigger invalidation (true negative) ---
    clause9_changes = [c for c in detected if c["clause_number"] == 9]
    clause9_ids = {c["change_id"] for c in clause9_changes}

    clause9_false_invalidation = any(
        s.get("invalidated_by_change_id") in clause9_ids
        for s in sign_offs
    )
    results.append({
        "check": "Clause 9 does NOT trigger invalidation (true negative)",
        "passed": not clause9_false_invalidation,
        "note": "OK" if not clause9_false_invalidation else "Clause 9 incorrectly caused an invalidation"
    })

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    score = passed / total

    return {"score": score, "passed": passed, "total": total, "results": results}


def print_report(eval_result: dict):
    print("\n" + "=" * 60)
    print("STATEFUL TRACKING EVAL — nexus_staylink v2->v3")
    print("=" * 60)

    for r in eval_result["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n[{status}] {r['check']}")
        print(f"       {r['note']}")

    pct = eval_result["score"] * 100
    print(f"\nSCORE: {eval_result['passed']}/{eval_result['total']} ({pct:.0f}%)")
    print("=" * 60 + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python evals/eval_stateful.py <path_to_pipeline_output.json>")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    state = load_pipeline_output(path)
    eval_result = evaluate(state)
    print_report(eval_result)

    sys.exit(0 if eval_result["score"] == 1.0 else 1)


if __name__ == "__main__":
    main()