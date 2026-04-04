# agents/policy_check.py
#
# Policy Check Agent
#
# Responsibility: check each material change against internal policy rules.
# Flags violations and near-misses. Does NOT make approval decisions.
#
# Input:  DEALtaState with detected_changes + routing_decisions populated
# Output: DEALtaState with policy_flags populated + agent trace appended

# Key design decision - a single change can produce multiple flags if it triggers multiple rules. C5 triggers both POL-001 and POL-007.
# That's intentional — one change, two separate accountability lines.

import json
import os
from datetime import datetime, timezone

from pydantic import ValidationError

from utils.instrumentation import instrumented_generate

from state.schema import (
    DEALtaState,
    PolicyFlag,
    AgentTrace,
)

SYSTEM_PROMPT = """You are a contract policy compliance specialist. Your job is to check
contract changes against a set of internal company policy rules and identify violations
or near-misses.

You must:
- Check each material change against ALL relevant policy rules
- Flag VIOLATIONS: where the change clearly breaches a policy rule
- Flag NEAR_MISSES: where the change approaches a policy boundary or creates
  ambiguity that requires human review (e.g. governing law changed to partner's
  local country — acceptable per policy but still needs Legal sign-off)
- Skip changes where no policy rule applies

Be precise. Name the rule being triggered. Explain exactly how the change
violates or approaches the rule. Do not flag things that are clearly within policy.

Where a single clause contains multiple changes with separate change_ids (e.g. C12 and C13 both in clause 15), flag each change_id independently against the applicable policy rules — do not merge them.

Return valid JSON only. No preamble."""


def build_policy_prompt(material_changes: list, policy_rules: list) -> str:
    return f"""{SYSTEM_PROMPT}

## MATERIAL CONTRACT CHANGES
{json.dumps(material_changes, indent=2)}

## POLICY RULES
{json.dumps(policy_rules, indent=2)}

For each material change, check it against all relevant policy rules.
Return only changes that trigger at least one rule.

Return a JSON array:
{{
  "change_id": "C4",
  "rule_id": "POL-007",
  "rule_name": "Credit Facility Reductions Require Finance Approval",
  "flag_type": "violation",
  "severity": "high",
  "explanation": "The credit facility was reduced from €50,000 to €25,000 without any Finance sign-off. This directly triggers POL-007.",
  "recommended_action": "Escalate to Finance for sign-off before accepting this change."
}}

flag_type values: "violation" | "near_miss"
A change may produce multiple entries if it triggers multiple rules.

Return only the JSON array."""


def run(state: DEALtaState) -> DEALtaState:
    print(f"[policy_check] Running on {state['contract_id']} {state['curr_version']}")

    # Load policy rules
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    policy_path = os.path.join(base, "policy", "rules.json")
    with open(policy_path) as f:
        policy_rules = json.load(f)

    material_changes = [
        c for c in state["detected_changes"]
        if c["change_type"] == "material"
    ]

    if not material_changes:
        print("[policy_check] No material changes to check.")
        trace = AgentTrace(
            agent="policy_check",
            version_processed=state["curr_version"],
            inputs_summary="No material changes",
            outputs_summary="No policy flags produced",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return {
            **state,
            "policy_flags": [],
            "agent_traces": state.get("agent_traces", []) + [trace],
            "pipeline_status": "policy_check_complete",
        }

    slim_changes = [
        {
            "change_id": c["change_id"],
            "clause_number": c["clause_number"],
            "clause_title": c["clause_title"],
            "materiality_level": c["materiality_level"],
            "v_prev_summary": c["v_prev_summary"],
            "v_curr_summary": c["v_curr_summary"],
            "raw_v_prev": c["raw_v_prev"],
            "raw_v_curr": c["raw_v_curr"],
            "detection_reasoning": c["detection_reasoning"],
        }
        for c in material_changes
    ]

    raw, metrics = instrumented_generate(build_policy_prompt(slim_changes, policy_rules), "policy_check")

    print("RAW RESPONSE:", raw)

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        flags_raw = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[policy_check] JSON parse failed: {e}")
        print(f"[policy_check] Raw response was: {raw[:500]}")
        raise RuntimeError(f"Agent failed to produce valid JSON. Raw: {raw[:200]}") from e

    policy_flags: list[dict] = []
    for flag in flags_raw:
        try:
            policy_flags.append(PolicyFlag(**flag).model_dump())
        except ValidationError as e:
            raise RuntimeError(
                f"[policy_check] PolicyFlag validation failed for {flag.get('change_id', '?')}: {e}"
            ) from e

    violations = sum(1 for f in policy_flags if f["flag_type"] == "violation")
    near_misses = sum(1 for f in policy_flags if f["flag_type"] == "near_miss")

    trace = AgentTrace(
        agent="policy_check",
        version_processed=state["curr_version"],
        inputs_summary=f"{len(material_changes)} material changes checked against {len(policy_rules)} rules",
        outputs_summary=f"{violations} violations, {near_misses} near-misses across {len(set(f['change_id'] for f in policy_flags))} changes",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    state["pipeline_metrics"].append(metrics)
    return {
        **state,
        "policy_flags": policy_flags,
        "agent_traces": state.get("agent_traces", []) + [trace],
        "pipeline_status": "policy_check_complete",
    }
