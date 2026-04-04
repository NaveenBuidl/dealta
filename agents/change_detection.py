# agents/change_detection.py
#
# Change Detection Agent
#
# Responsibility: compare two contract versions clause by clause,
# identify what changed, and classify each change as cosmetic or material.
#
# Input:  DEALtaState with prev_contract_text + curr_contract_text populated
# Output: DEALtaState with detected_changes populated + agent trace appended

# Key design decision - # Important rule inside prompt
# - CRITICAL: If a clause contains multiple legally distinct changes, you MUST create
#   separate entries for each. Example: a clause changing both governing law AND
#   jurisdiction must produce TWO separate entries — these are legally distinct even
#   though they appear in the same clause. Similarly, a clause that both reduces a
#   credit facility amount AND introduces a new volume-based trigger for further
#   reduction must produce TWO separate entries — the static reduction and the
#   dynamic trigger are distinct changes with different risk profiles.
# What is invalidated for, and why does it matter?
#  if Finance signed off on a credit facility term in v2, and then v3 arrives with a change that affects that same term, Finance's v2 sign-off is now void. The system marks it invalidated = True and records which change in v3 caused it.
# Why this matters: without invalidated, the system would carry forward stale approvals. v3 would look like it has Finance sign-off when that sign-off was based on assumptions that no longer hold. That's the exact failure mode DEALta is built to prevent.
# This is the core of Level 5. The whole stateful tracking session is about: how does the system know which sign-offs to invalidate when v3 arrives, and how does it surface that to the reviewer?


import json
import os
from datetime import datetime, timezone

from pydantic import ValidationError

from utils.instrumentation import instrumented_generate

# schema connection
from state.schema import (
    DEALtaState,
    ClauseChange,
    AgentTrace,
)
# model's job description
SYSTEM_PROMPT = """You are a contract change detection specialist. Your job is to compare
two versions of a contract clause by clause and classify every change with precision.

You distinguish between:
- COSMETIC changes: rewording, formatting, added definitions that don't shift obligations,
  legal-equivalent substitutions (e.g. "reasonable endeavours" vs "commercially reasonable
  efforts" under English law). These require no review.
- MATERIAL changes: shifts in obligations, rights, financial exposure, risk allocation,
  timeframes, liability, data handling, jurisdiction, or any change that affects what a
  party must do or can do. These require routing and review.

You must NOT flag changes that don't exist. Unchanged clauses are a test of precision.
You must NOT over-trigger on cosmetic language variation.
You must NOT under-trigger on substantive changes hidden in professional legal language.

Always return valid JSON. No preamble, no explanation outside the JSON."""

# STRENGTHENED: Gemini was merging C12/C13 (governing law + jurisdiction)
# into one entry despite being legally distinct. Added explicit example.

#  builds the full prompt sent to the model
def build_detection_prompt(prev_text: str, curr_text: str) -> str:
    return f"""{SYSTEM_PROMPT}

Compare these two contract versions and identify every clause-level change.

## PREVIOUS VERSION
{prev_text}

## CURRENT VERSION
{curr_text}

Return a JSON array of changes. For each change:

{{
  "change_id": "C1",
  "clause_number": 1,
  "clause_title": "Definitions",
  "change_type": "cosmetic" or "material",
  "materiality_level": "low" | "medium" | "high" | "critical",
  "v_prev_summary": "what the clause said before",
  "v_curr_summary": "what it says now",
  "raw_v_prev": "verbatim relevant text from previous version",
  "raw_v_curr": "verbatim relevant text from current version",
  "detection_reasoning": "why you classified it this way"
}}

Rules:
- Only include clauses that actually changed. Unchanged clauses must not appear.
- Materiality levels: low=minor operational, medium=process change, high=risk/obligation shift, critical=policy violation or major exposure
- Be specific in reasoning — name what obligation or right changed, not just that wording changed

# Important rule inside prompt
- CRITICAL: If a clause contains multiple legally distinct changes, you MUST create
  separate entries for each. Example: a clause changing both governing law AND
  jurisdiction must produce TWO separate entries — these are legally distinct even
  though they appear in the same clause. Similarly, a clause that both reduces a
  credit facility amount AND introduces a new volume-based trigger for further
  reduction must produce TWO separate entries — the static reduction and the
  dynamic trigger are distinct changes with different risk profiles.
  A clause that changes an existing value AND introduces a new conditional mechanism
  in the same edit MUST be two entries — the value change and the new mechanism are
  legally distinct regardless of appearing in the same clause.

Return only the JSON array. No other text."""

# This is what LangGraph calls - Take the current system state, do change detection, return updated state."
# This is the actual agent entrypoint.
def run(state: DEALtaState) -> DEALtaState:
    print(f"[change_detection] Running on {state['contract_id']} "
          f"{state['prev_version']} → {state['curr_version']}")

    raw, metrics = instrumented_generate(
        build_detection_prompt(
            state["prev_contract_text"],
            state["curr_contract_text"]
        ),
        "change_detection"
    )

    print("RAW RESPONSE:", raw)  # temporary debug line

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        changes_raw = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[change_detection] JSON parse failed: {e}")
        print(f"[change_detection] Raw response was: {raw[:500]}")
        raise RuntimeError(f"Agent failed to produce valid JSON. Raw: {raw[:200]}") from e

    detected_changes: list[dict] = []
    for c in changes_raw:
        try:
            detected_changes.append(ClauseChange(**c).model_dump())
        except ValidationError as e:
            raise RuntimeError(
                f"[change_detection] ClauseChange validation failed for {c.get('change_id', '?')}: {e}"
            ) from e

    trace = AgentTrace(
        agent="change_detection",
        version_processed=state["curr_version"],
        inputs_summary=f"Compared {state['prev_version']} vs {state['curr_version']}",
        outputs_summary=(
            f"Detected {len(detected_changes)} changes: "
            f"{sum(1 for c in detected_changes if c['change_type'] == 'material')} material, "
            f"{sum(1 for c in detected_changes if c['change_type'] == 'cosmetic')} cosmetic"
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    state["pipeline_metrics"].append(metrics)
    return {
        **state,
        "detected_changes": detected_changes,
        "agent_traces": state.get("agent_traces", []) + [trace],
        "pipeline_status": "change_detection_complete",
    }
