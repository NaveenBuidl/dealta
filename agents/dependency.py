# agents/dependency.py
#
# Dependency / Compound Risk Agent
#
# Responsibility: identify risks that ONLY emerge from the combination of two or
# more changes. Single-clause policy checks cannot catch these. This is the agent
# that makes DEALta more than a contract summarizer.
#
# Input:  DEALtaState with detected_changes + policy_flags populated
# Output: DEALtaState with compound_risks populated + agent trace appended

# DESIGN DECISION: Policy flag status and compound risk participation are independent.
# A change that is individually flagged can still participate in a compound risk.
# The dependency agent must never use "already flagged" as a reason to exclude a
# change from compound risk analysis. Individual flags capture single-clause risk.
# Compound risks capture emergent risk from combinations. These are separate concerns.
# Think of it like this: a doctor flags you for high blood pressure.
# That doesn't mean the doctor should ignore your blood pressure
# when checking whether the combination
# of blood pressure + high cholesterol + stress creates a heart attack risk.
# Each condition is flagged individually AND participates in the compound diagnosis.

# What the current compound risk agent actually does
# Looking at the prompt, it reasons about three things:
# What does each change remove or add in terms of rights, obligations, or protections?
# Does one change amplify the exposure created by another?
# Does the combination create something neither change creates alone?

import json
import os
from datetime import datetime, timezone

from pydantic import ValidationError

from utils.instrumentation import instrumented_generate


from state.schema import (
    DEALtaState,
    CompoundRisk,
    AgentTrace,
)


SYSTEM_PROMPT = """You are a contract risk analyst specialising in compound and
cross-clause risks. Your job is to identify risks that ONLY emerge from the
combination of two or more changes — risks that no single-clause review would catch.

CRITICAL RULE: For every compound risk you identify, you must be able to complete
this sentence: "Neither change creates this risk alone, but together they create X."
If you cannot complete that sentence, it is NOT a compound risk. Do not report it.

# Key Design Decision
IMPORTANT: A change that is individually favorable to one party can still
participate in a compound risk. Example: if Change A removes a partner's
unilateral power (favorable), but Change B halves a credit limit and Change C
adds a dynamic trigger on that limit, the combination of A+B+C removes the
reviewing party's ability to offset the financial pressure — A participates even
though it looks beneficial alone. Specifically: losing the ability to unilaterally
adjust commission rates (even if that loss is favorable in isolation) removes a
financial lever that could otherwise compensate for credit constraints elsewhere.

Do NOT:
- Report a compound risk whose description is already fully captured by a single
  policy flag (i.e. the combination adds nothing new beyond what's already flagged)
- Exclude a change from a compound risk just because it was individually flagged —
  a flagged change can still participate if the combination creates something new
- Describe what each change does in isolation
- List clauses without explaining what their combination uniquely produces
- Invent risks not supported by the actual clause text
- Pair changes that are in the SAME clause — two changes from clause 5 do not
  create a compound risk with each other. Compound risks require changes from
  DIFFERENT clauses combining to create emergent exposure.

DO:
- Focus on emergent effects: what does the combination enable, prevent, or create
  that no individual change does?
- Consider interactions across commercial, operational, and legal dimensions
- Look for cases where one change removes a protection and another amplifies the
  exposure, or where two changes together trap the reviewing party
- Consider three-change combinations, not just pairs. A risk involving changes
  from three different clauses is valid if the combination creates something none
  of the three creates alone.
- Search exhaustively. Do not stop after finding one compound risk. Review all
  possible cross-clause combinations before returning your answer.

Return valid JSON only. No preamble."""


def build_dependency_prompt(material_changes: list, policy_flags: list) -> str:
    return f"""{SYSTEM_PROMPT}

## MATERIAL CONTRACT CHANGES
{json.dumps(material_changes, indent=2)}

## POLICY FLAGS ALREADY RAISED
(These are single-clause risks already identified. Your job is what these miss.)
{json.dumps(policy_flags, indent=2)}

## COMBINATION GUIDANCE
When looking for compound risks, pay particular attention
to these cross-clause relationships:

- SLA degradation changes (resolution time increases)
  combined with termination right changes (cure periods,
  remediation plan requirements). An SLA change and a
  termination change together can trap a party — they must
  endure worse service AND face harder exit.

- Liability carve-out changes (removal of liability caps)
  combined with data protection changes (removal of DPA,
  shift from processor to controller). An uncapped liability
  combined with ambiguous data responsibilities creates
  exposure at the exact point where liability is highest.

These are the types of cross-clause interactions most
likely to create emergent risk. Do not limit yourself to
these — but ensure you have checked them before returning
your answer.

Analyse the changes above for compound risks — risks that only emerge from
combinations of two or more changes.

For each compound risk found, return:
{{
  "risk_id": "CR1",
  "change_ids": ["C7", "C11"],
  "description": "One sentence: what the combination creates that neither change creates alone.",
  "affected_functions": ["Legal", "Product/Tech"],
  "severity": "high",
  "reasoning": "C7 doubles P1 resolution time, meaning Nexus must endure longer outages. C11 adds a mandatory 30-day cure period before Nexus can exit on SLA grounds. Together: Nexus is trapped — it cannot exit quickly AND must absorb longer incidents. Neither clause alone creates the trap; the combination does."
}}

severity values: "low" | "medium" | "high" | "critical"
affected_functions values: "Legal" | "Commercial" | "Finance" | "Product/Tech" | "CS" | "Leadership"

If no genuine compound risks exist, return an empty array: []

Return only the JSON array."""


def run(state: DEALtaState) -> DEALtaState:
    print(f"[dependency] Running on {state['contract_id']} {state['curr_version']}")

    material_changes = [
        c for c in state["detected_changes"]
        if c["change_type"] == "material"
    ]

    if len(material_changes) < 2:
        print("[dependency] Fewer than 2 material changes — no compound risks possible.")
        trace = AgentTrace(
            agent="dependency_check",
            version_processed=state["curr_version"],
            inputs_summary="Fewer than 2 material changes",
            outputs_summary="No compound risks possible",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return {
            **state,
            "compound_risks": [],
            "agent_traces": state.get("agent_traces", []) + [trace],
            "pipeline_status": "dependency_check_complete",
        }

    # Pass only the fields the agent needs — keep token count down
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
        for c in material_changes
    ]

    slim_flags = [
        {
            "change_id": f["change_id"],
            "rule_id": f["rule_id"],
            "flag_type": f["flag_type"],
            "severity": f["severity"],
            "explanation": f["explanation"],
        }
        for f in state.get("policy_flags", [])
    ]

    raw, metrics = instrumented_generate(build_dependency_prompt(slim_changes, slim_flags), "dependency_check")

    print("RAW RESPONSE:", raw)

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        risks_raw = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[dependency] JSON parse failed: {e}")
        print(f"[dependency] Raw response was: {raw[:500]}")
        raise RuntimeError(f"Agent failed to produce valid JSON. Raw: {raw[:200]}") from e

    compound_risks: list[dict] = []
    for r in risks_raw:
        try:
            compound_risks.append(CompoundRisk(**r).model_dump())
        except ValidationError as e:
            raise RuntimeError(
                f"[dependency] CompoundRisk validation failed for {r.get('risk_id', '?')}: {e}"
            ) from e

    trace = AgentTrace(
        agent="dependency_check",
        version_processed=state["curr_version"],
        inputs_summary=f"{len(material_changes)} material changes + {len(slim_flags)} policy flags analysed",
        outputs_summary=f"{len(compound_risks)} compound risk(s) identified: {[r['risk_id'] for r in compound_risks]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    state["pipeline_metrics"].append(metrics)
    return {
        **state,
        "compound_risks": compound_risks,
        "agent_traces": state.get("agent_traces", []) + [trace],
        "pipeline_status": "dependency_check_complete",
    }
