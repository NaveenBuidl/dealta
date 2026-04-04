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
#   9. Commercial sign-off (SO-002) marked invalidated
#  10. SO-002 invalidation attributed to Clause 4 change
#  11. Legal sign-off (SO-003) marked invalidated
#  12. SO-003 invalidation attributed to Clause 9 change
#  13. SO-003 NOT invalidated by Clause 4 change (true negative)
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

    # --- Check 8: SO-001 and SO-002 NOT invalidated by Clause 9 change (true negative) ---
    clause9_changes = [c for c in detected if c["clause_number"] == 9]
    clause9_ids = {c["change_id"] for c in clause9_changes}

    finance_commercial_false = any(
        sf.get("invalidated_by_change_id") in clause9_ids
        for sf in sign_offs
        if sf.get("function") in ("Finance", "Commercial")
    )
    results.append({
        "check": "SO-001/SO-002 NOT invalidated by Clause 9 change (true negative)",
        "passed": not finance_commercial_false,
        "note": "OK" if not finance_commercial_false else "Finance or Commercial sign-off incorrectly attributed to Clause 9 change"
    })

    # --- Check 9: Commercial sign-off exists and is invalidated ---
    commercial_signoffs = [s for s in sign_offs if s.get("function") == "Commercial"]
    invalidated_commercial = [s for s in commercial_signoffs if s.get("invalidated") is True]

    commercial_invalidated = len(invalidated_commercial) > 0
    results.append({
        "check": "Commercial sign-off (SO-002) marked invalidated",
        "passed": commercial_invalidated,
        "note": "OK" if commercial_invalidated else (
            "No Commercial sign-off found" if not commercial_signoffs
            else "Commercial sign-off exists but invalidated is not True"
        )
    })

    # --- Check 10: SO-002 invalidated_by_change_id points to Clause 4 change ---
    so002_correct_cause = False
    if invalidated_commercial:
        clause4_changes = [c for c in detected if c["clause_number"] == 4]
        clause4_ids = {c["change_id"] for c in clause4_changes}

        for sf in invalidated_commercial:
            if sf.get("invalidated_by_change_id") in clause4_ids:
                so002_correct_cause = True
                break

    results.append({
        "check": "SO-002 invalidation attributed to Clause 4 change",
        "passed": so002_correct_cause,
        "note": "OK" if so002_correct_cause else (
            "invalidated_by_change_id does not point to a Clause 4 change"
            if invalidated_commercial else "No invalidated Commercial sign-off to check"
        )
    })

    # --- Check 11: Legal sign-off exists and is invalidated ---
    legal_signoffs = [s for s in sign_offs if s.get("function") == "Legal"]
    invalidated_legal = [s for s in legal_signoffs if s.get("invalidated") is True]

    legal_invalidated = len(invalidated_legal) > 0
    results.append({
        "check": "Legal sign-off (SO-003) marked invalidated",
        "passed": legal_invalidated,
        "note": "OK" if legal_invalidated else (
            "No Legal sign-off found" if not legal_signoffs
            else "Legal sign-off exists but invalidated is not True"
        )
    })

    # --- Check 12: SO-003 invalidated_by_change_id points to Clause 9 change ---
    so003_correct_cause = False
    if invalidated_legal:
        clause9_changes_for_so003 = [c for c in detected if c["clause_number"] == 9]
        clause9_ids_for_so003 = {c["change_id"] for c in clause9_changes_for_so003}

        for sf in invalidated_legal:
            if sf.get("invalidated_by_change_id") in clause9_ids_for_so003:
                so003_correct_cause = True
                break

    results.append({
        "check": "SO-003 invalidation attributed to Clause 9 change",
        "passed": so003_correct_cause,
        "note": "OK" if so003_correct_cause else (
            "invalidated_by_change_id does not point to a Clause 9 change"
            if invalidated_legal else "No invalidated Legal sign-off to check"
        )
    })

    # --- Check 13: SO-003 NOT invalidated by Clause 4 change (true negative) ---
    clause4_changes_check13 = [c for c in detected if c["clause_number"] == 4]
    clause4_ids_check13 = {c["change_id"] for c in clause4_changes_check13}

    so003_false_cause = any(
        sf.get("invalidated_by_change_id") in clause4_ids_check13
        for sf in invalidated_legal
    )
    results.append({
        "check": "SO-003 NOT invalidated by Clause 4 change (true negative)",
        "passed": not so003_false_cause,
        "note": "OK" if not so003_false_cause else "SO-003 incorrectly attributed to a Clause 4 change"
    })

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    score = passed / total

    return {"score": score, "passed": passed, "total": total, "results": results}


def print_report(eval_result: dict):
    print("\n" + "=" * 60)
    print("STATEFUL TRACKING EVAL (13 checks) — nexus_staylink v2->v3")
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