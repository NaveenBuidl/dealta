# evals/eval_policy_check.py

#> Tests: Quality primitive — does the system enforce rules correctly?
#
# Policy Check Agent Eval
# Metrics: violation detection rate, false positive rate, rule attribution accuracy
#
# Scoring keys on (clause_number, rule_id) — not change_id.
# Change IDs are assigned sequentially by the LLM and shift across runs.
# Clause numbers are stable (they come from the contract text itself).
# To get clause_number for a flag, the eval joins flag.change_id →
# state["detected_changes"] → clause_number.

import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from agents import change_detection, policy_check
from state.schema import DEALtaState

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_DIR = os.path.join(BASE, "contracts", "nexus_staylink", "v1_v2")
with open(os.path.join(CONTRACT_DIR, "nexus_staylink_v1.txt")) as f:
    v1 = f.read()
with open(os.path.join(CONTRACT_DIR, "nexus_staylink_v2.txt")) as f:
    v2 = f.read()

# Ground truth: set of (clause_number, rule_id) the agent must flag.
# Keyed by clause, not change_id — stable across runs.
# Notes on merges vs original change-id ground truth:
#   (5, POL-007): covers both C4 (static reduction) and C5 (volume trigger) —
#                 same clause, same rule; one match sufficient.
#   (15, POL-004): covers both C12 (governing law) and C13 (jurisdiction) —
#                  same clause, same rule; one match sufficient.
POLICY_GROUND_TRUTH = {
    (5,  "POL-007"),   # credit facility reduction + volume trigger
    (5,  "POL-001"),   # unilateral reduction right
    (7,  "POL-006"),   # P1 SLA degraded
    (9,  "POL-003"),   # asymmetric liability carve-out
    (11, "POL-005"),   # DPA removed
    (14, "POL-008"),   # termination gated on remediation plan
    (15, "POL-004"),   # governing law change + jurisdiction change
}

# Clauses that must NOT produce any flag (false positive sentinels)
NO_FLAG_CLAUSES = {4, 6, 12}
# clause 4 = commission shift (C3) — favorable to Nexus, must not be flagged
# clause 6 = pricing/MFN (C6) — cosmetic under English law
# clause 12 = confidentiality (C10) — cosmetic

initial_state: DEALtaState = {
    "contract_id": "nexus_staylink",
    "prev_version": "v1",
    "curr_version": "v2",
    "prev_contract_text": v1,
    "curr_contract_text": v2,
    "detected_changes": [],
    "routing_decisions": [],
    "policy_flags": [],
    "compound_risks": [],
    "issue_register": [],
    "sign_offs": [],
    "escalation_items": [],
    "agent_traces": [],
    "pipeline_metrics": [],
    "run_id": "eval-001",
    "run_timestamp": datetime.now(timezone.utc).isoformat(),
    "pipeline_status": "initiated",
}

state = change_detection.run(initial_state)
state = policy_check.run(state)

# Build change_id → clause_number lookup from this run's detected changes
clause_by_change = {c["change_id"]: c["clause_number"] for c in state["detected_changes"]}

# Keyed on (clause_number, rule_id) — change_ids are run-scoped and unstable
# Enrich agent flags with clause_number, group by (clause_number, rule_id)
agent_flagged = set()
flags_by_key = {}  # (clause_number, rule_id) → list of flags
for flag in state["policy_flags"]:
    clause_num = clause_by_change.get(flag["change_id"])
    if clause_num is None:
        print(f"[warn] Flag for change_id={flag['change_id']} not found in detected_changes — skipping")
        continue
    key = (clause_num, flag["rule_id"])
    agent_flagged.add(key)
    flags_by_key.setdefault(key, []).append(flag)

# Score
expected = POLICY_GROUND_TRUTH
true_positives = expected & agent_flagged
false_negatives = expected - agent_flagged
false_positives = agent_flagged - expected

print("\n" + "="*60)
print("POLICY CHECK EVAL — nexus_staylink v1→v2")
print("="*60)

print(f"\nExpected (clause, rule): {sorted(expected)}")
print(f"Agent flagged:           {sorted(agent_flagged)}")
print(f"\nDetection rate: {len(true_positives)}/{len(expected)} = {len(true_positives)/len(expected)*100:.0f}%")
if false_negatives:
    print(f"Missed:          {sorted(false_negatives)}")
if false_positives:
    print(f"False positives: {sorted(false_positives)}")

# Sentinel check: clauses that must never be flagged
for clause_num in NO_FLAG_CLAUSES:
    flagged_rules = [rule for (c, rule) in agent_flagged if c == clause_num]
    if flagged_rules:
        print(f"\n⚠️  Clause {clause_num} FALSELY FLAGGED with: {flagged_rules}")

# Detail
print("\n📋 FLAG DETAIL:")
for key in sorted(expected | agent_flagged):
    clause_num, rule_id = key
    status = "✓" if key in true_positives else ("✗ MISSED" if key in false_negatives else "✗ FALSE POS")
    print(f"\n   {status}  clause {clause_num} / {rule_id}:")
    for flag in flags_by_key.get(key, []):
        print(f"     change_id={flag['change_id']} [{flag['flag_type'].upper()}]: {flag['explanation'][:80]}...")

print("\n" + "="*60)
