# state/seed_signoffs.py
#
# Test scaffolding for Level 5.
# Reads the v1->v2 pipeline output and injects a synthetic Finance sign-off
# on the Commission Structure (Clause 4). This simulates what would happen
# in production when a human reviewer approves a change.
#
# Output: pipeline_output_v2_with_signoffs.json
# This file is the "previous state" the Level 5 pipeline loads.
#
# This is NOT a real agent. It exists because sign_offs is empty in the
# current pipeline output -- no agent writes to it yet. Step 3 creates
# the sign-off the invalidation agent needs something to invalidate.

import json
import os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load the v1->v2 pipeline output
input_path = os.path.join(BASE, "pipeline_output.json")
with open(input_path) as f:
    state = json.load(f)

# Find the Clause 4 (Commission Structure) change_id
clause4_change = next(
    (c for c in state["detected_changes"] if c["clause_number"] == 4),
    None
)

if not clause4_change:
    raise ValueError("Clause 4 not found in detected_changes. Check pipeline_output.json.")

print(f"Found Clause 4 change: {clause4_change['change_id']} — {clause4_change['clause_title']}")

# Synthetic Finance sign-off on the commission structure
synthetic_signoff = {
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

# Inject into state
state["sign_offs"] = [synthetic_signoff]

# Save
output_path = os.path.join(BASE, "pipeline_output_v2_with_signoffs.json")
with open(output_path, "w") as f:
    json.dump(state, f, indent=2)

print(f"Sign-off injected: {synthetic_signoff['signoff_id']}")
print(f"Function: {synthetic_signoff['function']}")
print(f"Conditions: {synthetic_signoff['conditions']}")
print(f"Saved to: pipeline_output_v2_with_signoffs.json")