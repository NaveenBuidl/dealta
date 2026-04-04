# evals/eval_routing.py

#> Tests: Control primitive — is routing logic correct?
#
# Routing Agent Eval
# Measures: routing accuracy against ground truth
# Metric: % of material changes routed to correct primary function

import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from agents import change_detection, routing
from state.schema import DEALtaState

# ── Load contracts ──────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_DIR = os.path.join(BASE, "contracts", "nexus_staylink", "v1_v2")
with open(os.path.join(CONTRACT_DIR, "nexus_staylink_v1.txt")) as f:
    v1 = f.read()
with open(os.path.join(CONTRACT_DIR, "nexus_staylink_v2.txt")) as f:
    v2 = f.read()

# ── Ground truth ─────────────────────────────────────────────────────────────
# Based on your eval output — these are the material changes only
ROUTING_GROUND_TRUTH = {
    "C3": {"primary": "Commercial",   "secondary": "Finance"},
    "C4": {"primary": "Finance",      "secondary": "Commercial"},
    "C5": {"primary": "Finance",      "secondary": None},
    "C7": {"primary": "Product/Tech", "secondary": "Customer Support"},
    "C8": {"primary": "Legal",        "secondary": "Product/Tech"},
    "C9": {"primary": "Legal",        "secondary": None},
    "C11": {"primary": "Legal",       "secondary": "Commercial"},
    "C12": {"primary": "Legal",       "secondary": "Leadership"},
    "C13": {"primary": "Legal",       "secondary": "Leadership"},
}

# ── Run pipeline ─────────────────────────────────────────────────────────────
initial_state: DEALtaState = {
    "contract_id": "nexus_staylink_001",
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
state = routing.run(state)

# ── Score ────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("ROUTING EVAL — nexus_staylink v1→v2")
print("="*60)

material_ids = set(ROUTING_GROUND_TRUTH.keys())
routed = {r["change_id"]: r for r in state["routing_decisions"]}

primary_correct = 0
primary_total = len(material_ids)

print("\n📋 ROUTING DETAIL:")
for change_id in sorted(material_ids):
    gt = ROUTING_GROUND_TRUTH[change_id]
    agent = routed.get(change_id)

    if not agent:
        print(f"   ✗ {change_id}: NOT ROUTED (missing)")
        continue

    agent_primary = agent["primary_function"]
    gt_primary = gt["primary"]
    correct = agent_primary == gt_primary

    if correct:
        primary_correct += 1

    mark = "✓" if correct else "✗"
    print(f"   {mark} {change_id}: agent={agent_primary} | gt={gt_primary}"
          + (f" | secondary={agent['secondary_function']}" if agent.get("secondary_function") else ""))
    if not correct:
        print(f"       reasoning: {agent['routing_reasoning'][:100]}...")

accuracy = primary_correct / primary_total * 100
print(f"\nPrimary routing accuracy: {accuracy:.0f}%  ({primary_correct}/{primary_total})")
print("="*60)