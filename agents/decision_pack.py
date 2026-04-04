# agents/decision_pack.py
#
# Decision Pack Agent
#
# Responsibility: synthesise outputs from all upstream agents into a single
# structured decision pack ready for commercial owner review.
#
# This is a SYNTHESIS agent — it does NOT do new reasoning.
# All fields except summary_narrative are deterministic Python logic.
# One LLM call is made at the end to produce a 2-3 sentence narrative.
#
# Input:  DEALtaState with all upstream agents complete
# Output: DEALtaState with decision_pack key populated

import json
from datetime import datetime, timezone

from utils.instrumentation import instrumented_generate
from state.schema import DEALtaState, AgentTrace

NARRATIVE_PROMPT = """You are reviewing a contract negotiation. Based on the following structured findings, write 2-3 sentences for the commercial owner. State the overall situation, the most critical issue, and what action is required. Be direct and specific. Max 150 words. Return plain text only — no markdown, no bullet points.

Findings:
{findings_json}"""


def _v(obj, key):
    """Get a field from a dict or Pydantic model."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def run(state: DEALtaState) -> DEALtaState:
    print(f"[decision_pack] Running on {state['contract_id']} {state['curr_version']}")

    detected_changes = state.get("detected_changes", [])
    routing_decisions = state.get("routing_decisions", [])
    policy_flags = state.get("policy_flags", [])
    compound_risks = state.get("compound_risks", [])
    sign_offs = state.get("sign_offs", [])
    pipeline_metrics = state.get("pipeline_metrics", [])

    # ------------------------------------------------------------------
    # Lookup maps built once, used everywhere below
    # ------------------------------------------------------------------
    change_id_to_clause = {
        _v(c, "change_id"): _v(c, "clause_number")
        for c in detected_changes
    }
    change_id_to_primary_fn = {
        _v(r, "change_id"): _v(r, "primary_function")
        for r in routing_decisions
    }

    # ------------------------------------------------------------------
    # overall_recommendation  (deterministic)
    # ------------------------------------------------------------------
    has_critical_flag = any(_v(f, "severity") == "critical" for f in policy_flags)
    has_invalidated_signoff = any(_v(s, "invalidated") is True for s in sign_offs)

    if has_critical_flag or has_invalidated_signoff:
        overall_recommendation = "ESCALATE"
    elif any(_v(f, "severity") == "high" for f in policy_flags):
        overall_recommendation = "NEGOTIATE"
    else:
        overall_recommendation = "APPROVE_WITH_CONDITIONS"

    # ------------------------------------------------------------------
    # invalidated_sign_offs  (filter sign_offs where invalidated=True)
    # ------------------------------------------------------------------
    invalidated_sign_offs = [
        s if isinstance(s, dict) else s.model_dump()
        for s in sign_offs
        if _v(s, "invalidated") is True
    ]

    # ------------------------------------------------------------------
    # critical_issues  (critical policy flags + invalidated sign-offs)
    # ------------------------------------------------------------------
    critical_issues = []

    for f in policy_flags:
        if _v(f, "severity") != "critical":
            continue
        cid = _v(f, "change_id")
        critical_issues.append({
            "change_id": cid,
            "clause": change_id_to_clause.get(cid),
            "description": _v(f, "explanation"),
            "policy_rule": _v(f, "rule_id"),
            "severity": "critical",
            "function": change_id_to_primary_fn.get(cid),
        })

    for s in invalidated_sign_offs:
        cid = _v(s, "invalidated_by_change_id")
        critical_issues.append({
            "change_id": cid,
            "clause": change_id_to_clause.get(cid),
            "description": (
                f"Sign-off {_v(s, 'signoff_id')} by {_v(s, 'function')} was "
                f"invalidated in {_v(s, 'invalidated_in_version')}"
            ),
            "policy_rule": None,
            "severity": "critical",
            "function": _v(s, "function"),
        })

    # ------------------------------------------------------------------
    # open_issues_count  (count policy_flags by severity)
    # ------------------------------------------------------------------
    open_issues_count = {"critical": 0, "high": 0, "medium": 0}
    for f in policy_flags:
        sev = _v(f, "severity")
        if sev in open_issues_count:
            open_issues_count[sev] += 1

    # ------------------------------------------------------------------
    # required_sign_offs  (derived from routing_decisions + sign_offs)
    # REQUIRED  = function flagged in routing, no sign-off present
    # CLEARED   = sign-off exists and not invalidated
    # INVALIDATED = sign-off exists and invalidated=True
    # ------------------------------------------------------------------
    flagged_functions: set[str] = set()
    for r in routing_decisions:
        pf = _v(r, "primary_function")
        sf = _v(r, "secondary_function")
        if pf:
            flagged_functions.add(pf)
        if sf:
            flagged_functions.add(sf)

    required_sign_offs: dict[str, str] = {}
    for fn in sorted(flagged_functions):
        fn_signoffs = [s for s in sign_offs if _v(s, "function") == fn]
        if not fn_signoffs:
            required_sign_offs[fn] = "REQUIRED"
        elif any(_v(s, "invalidated") is True for s in fn_signoffs):
            required_sign_offs[fn] = "INVALIDATED"
        else:
            required_sign_offs[fn] = "CLEARED"

    # ------------------------------------------------------------------
    # review_progress  (deterministic counts)
    # ------------------------------------------------------------------
    change_ids_with_flags = {_v(f, "change_id") for f in policy_flags}
    total_changes = len(detected_changes)
    changes_with_issues = sum(
        1 for c in detected_changes
        if _v(c, "change_id") in change_ids_with_flags
    )
    functions_pending = sum(1 for v in required_sign_offs.values() if v == "REQUIRED")
    functions_signed_off = sum(1 for v in required_sign_offs.values() if v == "CLEARED")

    review_progress = {
        "total_changes_detected": total_changes,
        "changes_with_issues": changes_with_issues,
        "changes_clean": total_changes - changes_with_issues,
        "functions_signed_off": functions_signed_off,
        "functions_pending": functions_pending,
    }

    # ------------------------------------------------------------------
    # escalation_items  (critical_issues + invalidated sign-offs as
    # structured list with type/change_id/clause/summary/decision_needed)
    # ------------------------------------------------------------------
    # Build a recommended_action lookup from policy_flags for quick access
    critical_flag_action = {
        _v(f, "change_id"): _v(f, "recommended_action")
        for f in policy_flags
        if _v(f, "severity") == "critical"
    }

    escalation_items = []
    for issue in critical_issues:
        if issue["policy_rule"] is not None:
            escalation_items.append({
                "type": "critical_policy_violation",
                "change_id": issue["change_id"],
                "clause": issue["clause"],
                "summary": issue["description"],
                "decision_needed": critical_flag_action.get(
                    issue["change_id"], "Review required before proceeding."
                ),
            })
        else:
            escalation_items.append({
                "type": "invalidated_sign_off",
                "change_id": issue["change_id"],
                "clause": issue["clause"],
                "summary": issue["description"],
                "decision_needed": "Re-review required — prior approval no longer valid.",
            })

    # ------------------------------------------------------------------
    # compound_risks  (pass-through — serialise Pydantic models if needed)
    # ------------------------------------------------------------------
    compound_risks_out = [
        cr if isinstance(cr, dict) else cr.model_dump()
        for cr in compound_risks
    ]

    # ------------------------------------------------------------------
    # commercial_alignment_check  (static)
    # ------------------------------------------------------------------
    commercial_alignment_check = (
        "NOT_AVAILABLE — requires pre-negotiation commercial charter as input. "
        "See DECISIONS.md."
    )

    # ------------------------------------------------------------------
    # summary_narrative  (one LLM call)
    # ------------------------------------------------------------------
    findings_for_narrative = {
        "overall_recommendation": overall_recommendation,
        "open_issues_count": open_issues_count,
        "critical_issues": critical_issues,
        "required_sign_offs": required_sign_offs,
        "compound_risks": [
            {
                "risk_id": _v(cr, "risk_id"),
                "description": _v(cr, "description"),
                "severity": _v(cr, "severity"),
            }
            for cr in compound_risks
        ],
        "escalation_items": escalation_items,
    }

    narrative_prompt = NARRATIVE_PROMPT.format(
        findings_json=json.dumps(findings_for_narrative, indent=2)
    )

    raw_narrative, metrics = instrumented_generate(narrative_prompt, "decision_pack")

    # Strip markdown fences if the model wrapped the text anyway
    if raw_narrative.startswith("```"):
        parts = raw_narrative.split("```")
        raw_narrative = parts[1] if len(parts) > 1 else raw_narrative
        # Drop language hint line (e.g. "text\n" or "json\n")
        if "\n" in raw_narrative:
            raw_narrative = raw_narrative[raw_narrative.index("\n") + 1:]
    summary_narrative = raw_narrative.strip()

    # ------------------------------------------------------------------
    # Assemble final decision_pack
    # ------------------------------------------------------------------
    decision_pack = {
        "overall_recommendation": overall_recommendation,
        "commercial_alignment_check": commercial_alignment_check,
        "summary_narrative": summary_narrative,
        "review_progress": review_progress,
        "escalation_items": escalation_items,
        "required_sign_offs": required_sign_offs,
        "invalidated_sign_offs": invalidated_sign_offs,
        "critical_issues": critical_issues,
        "open_issues_count": open_issues_count,
        "compound_risks": compound_risks_out,
        "pipeline_metrics": pipeline_metrics,
    }

    trace = AgentTrace(
        agent="decision_pack",
        version_processed=state["curr_version"],
        inputs_summary=(
            f"{total_changes} change(s), {len(policy_flags)} policy flag(s), "
            f"{len(compound_risks)} compound risk(s), {len(sign_offs)} sign-off(s)"
        ),
        outputs_summary=(
            f"Recommendation: {overall_recommendation}. "
            f"{len(critical_issues)} critical issue(s). "
            f"{functions_pending} function(s) REQUIRED."
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    pipeline_metrics.append(metrics)

    return {
        **state,
        "decision_pack": decision_pack,
        "pipeline_metrics": pipeline_metrics,
        "pipeline_status": "decision_pack_ready",
        "agent_traces": state.get("agent_traces", []) + [trace],
    }
