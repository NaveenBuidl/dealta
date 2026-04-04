# evals/eval_change_detection.py
#> Tests: Information primitive — is context extraction correct?
#
# Evaluates the Change Detection agent against ground_truth.json.
# Run this before wiring the agent into LangGraph.
#
# Metrics:
#   - Precision: of changes flagged, how many are real?
#   - Recall: of real changes, how many were caught?
#   - Classification accuracy: of caught changes, how many typed correctly?
#   - False negatives: real changes the agent missed (dangerous)
#   - False positives: hallucinated changes (noisy but less dangerous)

import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.change_detection import run
from state.schema import DEALtaState
from datetime import datetime, timezone


def load_file(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def load_ground_truth(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def evaluate():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts", "nexus_staylink", "v1_v2")

    state = DEALtaState(
        contract_id="nexus_staylink",
        prev_version="v1",
        curr_version="v2",
        prev_contract_text=load_file(os.path.join(base, "nexus_staylink_v1.txt")),
        curr_contract_text=load_file(os.path.join(base, "nexus_staylink_v2.txt")),
        detected_changes=[],
        routing_decisions=[],
        policy_flags=[],
        compound_risks=[],
        issue_register=[],
        sign_offs=[],
        escalation_items=[],
        agent_traces=[],
        pipeline_metrics=[],
        run_id="eval-001",
        run_timestamp=datetime.now(timezone.utc).isoformat(),
        pipeline_status="initiated",
    )

    # Run the agent
    result = run(state)
    detected = result["detected_changes"]

    # Load ground truth
    gt = load_ground_truth(os.path.join(base, "ground_truth.json"))
    gt_changes = {c["change_id"]: c for c in gt["changes"]}

    # Ground truth sets
    gt_material_ids = {
        cid for cid, c in gt_changes.items() if c["change_type"] == "material"
    }
    gt_cosmetic_ids = {
        cid for cid, c in gt_changes.items() if c["change_type"] == "cosmetic"
    }
    gt_all_ids = set(gt_changes.keys())

    # What the agent produced (match by clause number since IDs may differ)
    # Map agent output by clause_number for comparison
    agent_by_clause = {c["clause_number"]: c for c in detected}
    gt_by_clause = {c["clause_number"]: c for c in gt["changes"]}

    detected_clause_nums = set(agent_by_clause.keys())
    gt_clause_nums = set(gt_by_clause.keys())

    true_positives = detected_clause_nums & gt_clause_nums
    false_positives = detected_clause_nums - gt_clause_nums
    false_negatives = gt_clause_nums - detected_clause_nums

    precision = len(true_positives) / len(detected_clause_nums) if detected_clause_nums else 0
    recall = len(true_positives) / len(gt_clause_nums) if gt_clause_nums else 0

    # Classification accuracy on true positives
    correct_type = 0
    for clause_num in true_positives:
        agent_type = agent_by_clause[clause_num]["change_type"]
        gt_type = gt_by_clause[clause_num]["change_type"]
        if agent_type == gt_type:
            correct_type += 1

    type_accuracy = correct_type / len(true_positives) if true_positives else 0

    # Print results
    print("\n" + "="*60)
    print("CHANGE DETECTION EVAL — nexus_staylink v1→v2")
    print("="*60)
    print(f"\nGround truth:  {len(gt_clause_nums)} changes across {len(gt_clause_nums)} clauses")
    print(f"Agent found:   {len(detected_clause_nums)} changes")
    print(f"\nPrecision:     {precision:.0%}  ({len(true_positives)}/{len(detected_clause_nums)} flagged changes are real)")
    print(f"Recall:        {recall:.0%}  ({len(true_positives)}/{len(gt_clause_nums)} real changes caught)")
    print(f"Type accuracy: {type_accuracy:.0%}  ({correct_type}/{len(true_positives)} correctly typed as cosmetic/material)")

    if false_negatives:
        print(f"\n⚠️  FALSE NEGATIVES (missed — most dangerous):")
        for cn in sorted(false_negatives):
            gt_c = gt_by_clause[cn]
            print(f"   Clause {cn} ({gt_c['clause_title']}) — {gt_c['change_type'].upper()}")
            print(f"   Expected: {gt_c['v2_summary']}")

    if false_positives:
        print(f"\n🔶 FALSE POSITIVES (hallucinated changes):")
        for cn in sorted(false_positives):
            a_c = agent_by_clause[cn]
            print(f"   Clause {cn} ({a_c['clause_title']}) — {a_c['change_type'].upper()}")
            print(f"   Agent said: {a_c['v_curr_summary']}")

    print(f"\n📋 CLASSIFICATION DETAIL (true positives):")
    for cn in sorted(true_positives):
        a = agent_by_clause[cn]
        g = gt_by_clause[cn]
        match = "✓" if a["change_type"] == g["change_type"] else "✗"
        print(f"   {match} Clause {cn} ({g['clause_title']}): "
              f"agent={a['change_type']} | gt={g['change_type']}")

    print("\n" + "="*60)
    return precision, recall, type_accuracy


if __name__ == "__main__":
    evaluate()
