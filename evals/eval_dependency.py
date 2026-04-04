# evals/eval_dependency.py

#> Tests: Intelligence primitive — can the model reason across inputs?
#
# Evaluation: Compound Risk Detection
#
# Ground truth (v2->v3): CR1 (clause 4 + clause 5), CR2 (clause 5 + clause 9)
# Scoring: a compound risk is correct if:
#   1. The required clause numbers are all covered (order-independent)
#   2. The severity is not critically wrong (high/critical both acceptable for serious risks)
#   3. Extra detected risks beyond the planted CRs do NOT cause failures
#
# Matching on clause numbers (not change_ids) makes the eval robust across
# model runs that assign IDs dynamically.
# Note -
# Change IDs differ because they're assigned dynamically by the LLM on each run.
# The model might call it C4 one run and C6 the next run depending on how it counts.
# They're not stable across runs.
# Clause numbers are also unstable across contract versions — you're right about that.
# But within a single eval run comparing v2 to v3, the clause numbers in the contract text are fixed.
# The eval is checking one specific run, not comparing across versions.
# So clause numbers are stable enough for matching within that run.
# The choice was: clause numbers are unstable across versions but stable within a run.
# Change IDs are unstable even within a run. Clause numbers are the less bad option.


import json
import sys
import os

# ---------------------------------------------------------------------------
# Ground truth — clause numbers sourced from ground_truth.json
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    {
        "risk_id": "CR1",
        "required_clause_numbers": {4, 5},
        "min_entries_per_clause": {},
        "description": "Commission control lost + API suspension right = Nexus loses commercial lever to recover volume while simultaneously facing service suspension if volume drops",
        "expected_severity_min": "high",
    },
    {
        "risk_id": "CR2",
        "required_clause_numbers": {5, 9},
        "min_entries_per_clause": {},
        "description": "API suspension right + uncapped liability for volume shortfall = StayLink can suspend service on volume grounds then pursue unlimited damages for that same volume shortfall",
        "expected_severity_min": "high",
    },
]

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def load_pipeline_output(path: str) -> tuple[list, dict]:
    """Load compound_risks and a change_id->clause_number map from pipeline output."""
    with open(path) as f:
        state = json.load(f)
    compound_risks = state.get("compound_risks", [])
    id_to_clause = {
        c["change_id"]: c["clause_number"]
        for c in state.get("detected_changes", [])
    }
    return compound_risks, id_to_clause


def evaluate(compound_risks: list, id_to_clause: dict) -> dict:
    results = []

    for gt in GROUND_TRUTH:
        match = None

        for detected in compound_risks:
            detected_ids = detected.get("change_ids", [])
            clause_numbers = [id_to_clause[cid] for cid in detected_ids if cid in id_to_clause]

            # All required clause numbers must be covered
            if not gt["required_clause_numbers"].issubset(set(clause_numbers)):
                continue

            # Per-clause minimum entry counts (e.g. clause 5 must appear twice for CR2)
            ok = all(
                clause_numbers.count(cn) >= min_count
                for cn, min_count in gt["min_entries_per_clause"].items()
            )
            if not ok:
                continue

            match = detected
            break

        if match is None:
            results.append({
                "risk_id": gt["risk_id"],
                "found": False,
                "correct_clauses": False,
                "severity_ok": False,
                "detected_risk_id": None,
                "note": f"No detected risk covered clause numbers {sorted(gt['required_clause_numbers'])}",
            })
            continue

        detected_severity = match.get("severity", "low")
        severity_ok = (
            SEVERITY_RANK.get(detected_severity, 0)
            >= SEVERITY_RANK.get(gt["expected_severity_min"], 0)
        )

        matched_clause_nums = [id_to_clause[cid] for cid in match.get("change_ids", []) if cid in id_to_clause]

        results.append({
            "risk_id": gt["risk_id"],
            "found": True,
            "correct_clauses": True,
            "severity_ok": severity_ok,
            "detected_risk_id": match.get("risk_id"),
            "detected_change_ids": list(match.get("change_ids", [])),
            "detected_clause_numbers": matched_clause_nums,
            "detected_severity": detected_severity,
            "note": "OK" if severity_ok else f"Severity too low: got {detected_severity}, expected >= {gt['expected_severity_min']}",
        })

    correct = sum(1 for r in results if r["found"] and r["severity_ok"])
    total = len(GROUND_TRUTH)
    score = correct / total if total > 0 else 0.0

    return {
        "score": score,
        "correct": correct,
        "total": total,
        "results": results,
    }


def print_report(eval_result: dict, compound_risks: list):
    print("\n" + "=" * 60)
    print("COMPOUND RISK DETECTION EVAL")
    print("=" * 60)
    print(f"\nDetected {len(compound_risks)} compound risk(s) total\n")

    for r in eval_result["results"]:
        status = "PASS" if r["found"] and r["severity_ok"] else "FAIL"
        print(f"[{status}] {r['risk_id']}")
        if r["found"]:
            print(f"       Matched detected risk: {r['detected_risk_id']}")
            print(f"       change_ids: {r['detected_change_ids']}")
            print(f"       clause numbers: {r['detected_clause_numbers']}")
            print(f"       severity: {r['detected_severity']}")
        print(f"       Note: {r['note']}")
        print()

    pct = eval_result["score"] * 100
    print(f"SCORE: {eval_result['correct']}/{eval_result['total']} ({pct:.0f}%)")
    print("=" * 60 + "\n")

    print("DETECTED COMPOUND RISKS (full output):")
    for cr in compound_risks:
        print(f"\n  {cr.get('risk_id', '?')} — {cr.get('description', '')}")
        print(f"  change_ids: {cr.get('change_ids', [])}")
        print(f"  severity: {cr.get('severity', '?')}")
        print(f"  affected_functions: {cr.get('affected_functions', [])}")
        print(f"  reasoning: {cr.get('reasoning', '')[:300]}...")


def main():
    if len(sys.argv) < 2:
        print("Usage: python evals/eval_dependency.py <path_to_pipeline_output.json>")
        print("\nExpected: pipeline output JSON with 'compound_risks' and 'detected_changes' keys")
        sys.exit(1)

    output_path = sys.argv[1]
    if not os.path.exists(output_path):
        print(f"File not found: {output_path}")
        sys.exit(1)

    compound_risks, id_to_clause = load_pipeline_output(output_path)
    eval_result = evaluate(compound_risks, id_to_clause)
    print_report(eval_result, compound_risks)

    sys.exit(0 if eval_result["score"] == 1.0 else 1)


if __name__ == "__main__":
    main()
