# agents/routing.py
#
# Routing Agent
#
# Responsibility: for each material change detected, decide which business
# function(s) should review it. Cosmetic changes are skipped.
#
# Input:  DEALtaState with detected_changes populated
# Output: DEALtaState with routing_decisions populated + agent trace appended

# Key design decision - Single responsibility: change detection's job is to identify and classify changes. The moment you add routing logic to it, the prompt gets longer, the task gets harder, and failures become harder to diagnose. If routing is wrong, you don't know if the problem is in the detection logic or the routing logic.
# Separation enables independent evaluation. You can score change detection at 100% and routing at 89% separately. If they were merged, a routing error would look like a detection error. You'd have no way to isolate where the problem is.
# This is the core reason DEALta is multi-agent instead of one big prompt. Each agent has a narrow job, a clear input, a clear output, and its own eval. When something breaks, you know exactly where to look.

import json
import os
from datetime import datetime, timezone

from utils.instrumentation import instrumented_generate

from state.schema import (
    DEALtaState,
    RoutingDecision,
    AgentTrace,
)

VALID_FUNCTIONS = ["Legal", "Commercial", "Finance", "Product/Tech", "Customer Support", "Leadership"]

SYSTEM_PROMPT = """You are a contract routing specialist at a B2B travel technology company.
Your job is to read a contract change and decide which internal business function(s) must review it.

Business functions:
- Legal: governing law, jurisdiction, liability, data protection, GDPR, IP, termination clauses
- Commercial: commission structures, partnership terms, exclusivity, volume commitments, pricing
- Finance: payment terms, credit facilities, invoicing, financial exposure, penalties
- Product/Tech: API requirements, SLAs, integration specs, technical standards, security obligations. SLA incident response times and resolution windows are owned by Product/Tech, not CS.
- Customer Support: Customer-facing impact of service degradation. CS is secondary when SLA changes affect customer experience — Product/Tech is always primary for SLA ownership.
- Leadership: critical liability exposure, escalation items, strategic risk. Leadership is always secondary — they receive escalations, they do not own clause review. Governing law and jurisdiction changes are owned by Legal, not Leadership.

Rules:
- Only route material changes. Cosmetic changes must not appear in your output.
- Every material change gets exactly one primary_function.
- secondary_function is optional — only include it if a second team genuinely needs to review.
- Be specific in routing_reasoning: name what the change affects and why that function owns it.

Return valid JSON only. No preamble."""


def build_routing_prompt(material_changes: list) -> str:
    changes_text = json.dumps(material_changes, indent=2)
    return f"""{SYSTEM_PROMPT}

Route each of these material contract changes to the appropriate business function(s).

## MATERIAL CHANGES
{changes_text}

Return a JSON array. One entry per change_id:

{{
  "change_id": "C3",
  "primary_function": "Commercial",
  "secondary_function": "Finance",
  "routing_reasoning": "Commission rate amendment mechanism shifts from unilateral to mutual — Commercial owns this relationship, Finance needs to assess rate lock risk."
}}

Valid function values: {VALID_FUNCTIONS}
secondary_function can be null if no second function is needed.

Return only the JSON array."""


def run(state: DEALtaState) -> DEALtaState:
    print(f"[routing] Running on {state['contract_id']} {state['curr_version']}")

    material_changes = [
        c for c in state["detected_changes"]
        if c["change_type"] == "material"
    ]

    if not material_changes:
        print("[routing] No material changes to route.")
        trace = AgentTrace(
            agent="routing",
            version_processed=state["curr_version"],
            inputs_summary="No material changes detected",
            outputs_summary="No routing decisions produced",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return {
            **state,
            "routing_decisions": [],
            "agent_traces": state.get("agent_traces", []) + [trace],
            "pipeline_status": "routing_complete",
        }

    # Only pass the fields the routing agent needs — not the full raw text
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

    raw, metrics = instrumented_generate(build_routing_prompt(slim_changes), "routing")

    print("RAW RESPONSE:", raw)

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
  
    try:
        routing_raw = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[routing] JSON parse failed: {e}")
        print(f"[routing] Raw response was: {raw[:500]}")
        raise RuntimeError(f"Agent failed to produce valid JSON. Raw: {raw[:200]}") from e


    routing_decisions: list[RoutingDecision] = []
    for r in routing_raw:
        routing_decisions.append(RoutingDecision(
            change_id=r["change_id"],
            primary_function=r.get("primary_function"),
            secondary_function=r.get("secondary_function"),
            routing_reasoning=r["routing_reasoning"],
        ))

    routed_ids = [r["change_id"] for r in routing_decisions]
    trace = AgentTrace(
        agent="routing",
        version_processed=state["curr_version"],
        inputs_summary=f"{len(material_changes)} material changes",
        outputs_summary=f"Routed {len(routing_decisions)} changes: {routed_ids}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    state["pipeline_metrics"].append(metrics)
    return {
        **state,
        "routing_decisions": routing_decisions,
        "agent_traces": state.get("agent_traces", []) + [trace],
        "pipeline_status": "routing_complete",
    }