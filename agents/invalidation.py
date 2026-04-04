# agents/invalidation.py
#
# Invalidation Agent
#
# Responsibility: given v3 detected changes and v2 sign-offs loaded from
# previous pipeline output, determine which sign-offs are invalidated by
# the new changes.
#
# This is what makes DEALta stateful. v3 doesn't start from zero --
# it inherits v2 approvals and checks whether new changes void them.
#
# Input:  DEALtaState with detected_changes + sign_offs populated
# Output: DEALtaState with sign_offs updated (invalidated fields set)
#
# Design decision: Option A (clause-match) as baseline.
# If a v3 change touches a clause that a sign-off was based on,
# OR if the sign-off conditions explicitly reference the changed clause,
# the agent reasons about whether the assumptions are broken.
# Start simple, refine if eval fails.

#TODO rename to compound_risk.py and agent trace to "compound_risk" after Level 7

import json
from datetime import datetime, timezone

from utils.instrumentation import instrumented_generate
from state.schema import DEALtaState, AgentTrace

SYSTEM_PROMPT = """You are a contract review specialist responsible for tracking 
sign-off validity across negotiation rounds.

Your job: given a set of new contract changes (v3) and a set of existing sign-offs 
from a previous review (v2), determine which sign-offs are no longer valid.

A sign-off is invalidated when a new change affects the assumptions it was based on.
This can happen in two ways:

DIRECT: The new change modifies the same clause the sign-off approved.

INDIRECT: The new change modifies a different clause, but that clause was part of 
the commercial or legal context the sign-off implicitly assumed. 

For example: Finance approved commission terms assuming SLA degradation was already 
at its worst. A further SLA degradation changes the risk profile Finance was 
approving against -- even though SLA is a different clause. That is an indirect 
invalidation.

For each sign-off, reason carefully:
1. What did the approving function actually agree to?
2. What assumptions did that approval rest on -- stated in the conditions field?
3. Do any of the new v3 changes break those assumptions, directly or indirectly?

Be precise. Not every change invalidates every sign-off. Only mark invalidated 
when you can clearly complete this sentence: "The approval was based on X, 
but v3 changed Y, which means X no longer holds."

Return valid JSON only. No preamble."""


def build_invalidation_prompt(detected_changes: list, sign_offs: list) -> str:
    return f"""{SYSTEM_PROMPT}

## V3 DETECTED CHANGES
{json.dumps(detected_changes, indent=2)}

## V2 SIGN-OFFS (from previous review round)
{json.dumps(sign_offs, indent=2)}

For each sign-off, determine if any v3 change invalidates it.

Return a JSON array -- one entry per sign-off:

{{
  "signoff_id": "SO-001",
  "invalidated": true,
  "invalidated_by_change_id": "C1",
  "invalidated_in_version": "v3",
  "invalidation_reasoning": "Finance approved commission terms assuming SLA was at 8 hours. v3 degrades P1 to 12 hours, changing the commercial risk profile Finance was approving against."
}}

If a sign-off is NOT invalidated:
{{
  "signoff_id": "SO-001", 
  "invalidated": false,
  "invalidated_by_change_id": null,
  "invalidated_in_version": null,
  "invalidation_reasoning": "No v3 change affects the assumptions behind this approval."
}}

Return only the JSON array. One entry per sign-off."""


def run(state: DEALtaState) -> DEALtaState:
    print(f"[invalidation] Running on {state['contract_id']} {state['curr_version']}")

    sign_offs = state.get("sign_offs", [])

    if not sign_offs:
        print("[invalidation] No sign-offs to check. Skipping.")
        trace = AgentTrace(
            agent="invalidation",
            version_processed=state["curr_version"],
            inputs_summary="No sign-offs in state",
            outputs_summary="No invalidation checks performed",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return {
            **state,
            "agent_traces": state.get("agent_traces", []) + [trace],
            "pipeline_status": "change_detection_complete",
        }

    detected_changes = state.get("detected_changes", [])

    # Pass slim version of changes to keep token count down
    slim_changes = [
        {
            "change_id": c["change_id"],
            "clause_number": c["clause_number"],
            "clause_title": c["clause_title"],
            "materiality_level": c["materiality_level"],
            "v_prev_summary": c["v_prev_summary"],
            "v_curr_summary": c["v_curr_summary"],
            "detection_reasoning": c["detection_reasoning"],
        }
        for c in detected_changes
        if c["change_type"] == "material"
    ]

    raw, metrics = instrumented_generate(
        build_invalidation_prompt(slim_changes, sign_offs),
        "invalidation"
    )

    print("RAW RESPONSE:", raw)

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
  
    try:
        invalidation_results = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[invalidation] JSON parse failed: {e}")
        print(f"[invalidation] Raw response was: {raw[:500]}")
        raise RuntimeError(f"Agent failed to produce valid JSON. Raw: {raw[:200]}") from e

    # Update sign_offs in state with invalidation decisions
    updated_sign_offs = []
    for sign_off in sign_offs:
        sid = sign_off["signoff_id"]
        result = next(
            (r for r in invalidation_results if r["signoff_id"] == sid),
            None
        )
        if result and result.get("invalidated"):
            updated = {
                **sign_off,
                "invalidated": True,
                "invalidated_by_change_id": result.get("invalidated_by_change_id"),
                "invalidated_in_version": result.get("invalidated_in_version", state["curr_version"]),
            }
            print(f"[invalidation] {sid} INVALIDATED by {result.get('invalidated_by_change_id')}")
        else:
            updated = {**sign_off, "invalidated": False}
            print(f"[invalidation] {sid} still valid")
        updated_sign_offs.append(updated)

    invalidated_count = sum(1 for s in updated_sign_offs if s["invalidated"])

    trace = AgentTrace(
        agent="invalidation",
        version_processed=state["curr_version"],
        inputs_summary=f"{len(slim_changes)} material changes checked against {len(sign_offs)} sign-off(s)",
        outputs_summary=f"{invalidated_count} sign-off(s) invalidated",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    state["pipeline_metrics"].append(metrics)
    return {
        **state,
        "sign_offs": updated_sign_offs,
        "agent_traces": state.get("agent_traces", []) + [trace],
        "pipeline_status": "change_detection_complete",
    }