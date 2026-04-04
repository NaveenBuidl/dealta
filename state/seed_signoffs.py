# state/seed_signoffs.py
#
# Test scaffolding for Level 5.
# Reads the v1->v2 pipeline output and injects 3 synthetic sign-offs:
#   SO-001 — Finance on Clause 4 (Commission Structure)
#   SO-002 — Commercial on Clause 4 (Commission Structure)
#   SO-003 — Legal on Clause 9 (Liability & Limitation of Liability)
# This simulates what would happen in production when human reviewers approve changes.
#
# Output: outputs/pipeline_output_v2_with_3_signoffs.json
# This file is the "previous state" the Level 5 pipeline loads.
#
# This is NOT a real agent. It exists because sign_offs is empty in the
# current pipeline output -- no agent writes to it yet. This script creates
# the sign-offs the invalidation agent needs something to invalidate.

import json
import os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load the v1->v2 pipeline output
input_path = os.path.join(BASE, "outputs", "pipeline_output_nexus_staylink_001_v2.json")
with open(input_path) as f:
    state = json.load(f)

# Find the Clause 4 (Commission Structure) change_id
clause4_change = next(
    (c for c in state["detected_changes"] if c["clause_number"] == 4),
    None
)

if not clause4_change:
    raise ValueError("Clause 4 not found in detected_changes. Check pipeline_output_nexus_staylink_001_v2.json.")

print(f"Found Clause 4 change: {clause4_change['change_id']} — {clause4_change['clause_title']}")

# Find the Clause 9 (Liability & Limitation of Liability) change_id
clause9_change = next(
    (c for c in state["detected_changes"] if c["clause_number"] == 9),
    None
)
if not clause9_change:
    raise ValueError("Clause 9 not found in detected_changes.")
print(f"Found Clause 9 change: {clause9_change['change_id']} — {clause9_change['clause_title']}")

# SO-001 — Finance on Clause 4 (Commission Structure)
so_001 = {
    "signoff_id": "SO-001",
    "function": "Finance",
    "issue_id": "ISS-001",
    "approved": True,
    "conditions": """Approved subject to:
    (1) commission review mechanism remaining Nexus-initiated or mutually triggered —
    any shift to unilateral StayLink control  of commission reviews requires Finance re-review;
    (2) SLA terms remaining at v2  levels;
    (3) no new unilateral rights introduced affecting service continuity or commercial terms that
    would alter the risk profile of the commission structure.""",
    "signed_off_in_version": "v2",
    "invalidated": False,
    "invalidated_by_change_id": None,
    "invalidated_in_version": None,
    "timestamp": datetime.now(timezone.utc).isoformat()
}

# SO-002 — Commercial on Clause 4 (Commission Structure)
so_002 = {
    "signoff_id": "SO-002",
    "function": "Commercial",
    "issue_id": "ISS-002",
    "approved": True,
    "conditions": "Approved subject to commission amendments remaining mutually agreed between both parties. Any shift to unilateral partner control of commission review timing, frequency, or methodology requires Commercial re-review.",
    "signed_off_in_version": "v2",
    "invalidated": False,
    "invalidated_by_change_id": None,
    "invalidated_in_version": None,
    "timestamp": datetime.now(timezone.utc).isoformat()
}

# SO-003 — Legal on Clause 9 (Liability & Limitation of Liability)
so_003 = {
    "signoff_id": "SO-003",
    "function": "Legal",
    "issue_id": "ISS-003",
    "approved": True,
    "conditions": "Approved subject to liability cap carve-out remaining limited to API security implementation failures only. Any expansion of carve-out scope to cover commercial performance, volume thresholds, or other non-security triggers requires Legal re-review.",
    "signed_off_in_version": "v2",
    "invalidated": False,
    "invalidated_by_change_id": None,
    "invalidated_in_version": None,
    "timestamp": datetime.now(timezone.utc).isoformat()
}

# Inject into state
state["sign_offs"] = [so_001, so_002, so_003]

# Save
output_path = os.path.join(BASE, "outputs", "pipeline_output_v2_with_3_signoffs.json")
with open(output_path, "w") as f:
    json.dump(state, f, indent=2)

print(f"Sign-off injected: {so_001['signoff_id']} — {so_001['function']}")
print(f"Sign-off injected: {so_002['signoff_id']} — {so_002['function']}")
print(f"Sign-off injected: {so_003['signoff_id']} — {so_003['function']}")
print(f"Saved to: {output_path}")
