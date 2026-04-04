"""
ui/app.py — DEALta Streamlit demo UI

Rendering layer only. Reads outputs/pipeline_output_nexus_staylink_001_v3.json
and renders results. No agent imports, no LLM calls, no pipeline logic.

Run from repo root:
    streamlit run ui/app.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


def status_badge(label: str) -> str:
    colours = {
        "REQUIRED": ("#E53935", "#fff"),
        "INVALIDATED": ("#FB8C00", "#fff"),
        "CLEARED": ("#43A047", "#fff"),
        "NOT_REQUIRED": ("#9E9E9E", "#fff"),
        "ESCALATE": ("#E53935", "#fff"),
        "NEGOTIATE": ("#FB8C00", "#fff"),
        "APPROVE_WITH_CONDITIONS": ("#43A047", "#fff"),
        "CRITICAL": ("#E53935", "#fff"),
        "HIGH": ("#FB8C00", "#fff"),
        "MEDIUM": ("#F9A825", "#000"),
        "LOW": ("#9E9E9E", "#fff"),
    }
    bg, fg = colours.get(label.upper(), ("#EEEEEE", "#333"))
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 10px;'
        f'border-radius:12px;font-size:13px;font-weight:600;'
        f'white-space:nowrap">{label}</span>'
    )


st.set_page_config(page_title="DEALta", layout="wide")

ROOT = Path(__file__).parent.parent
OUTPUT_FILE = ROOT / "outputs" / "pipeline_output_nexus_staylink_001_v3.json"

ALL_FUNCTIONS = ["Commercial", "Finance", "Legal", "Product/Tech", "Tax", "CS"]

# ---------------------------------------------------------------------------
# Load pipeline output
# ---------------------------------------------------------------------------
data = None
load_error = False

if OUTPUT_FILE.exists():
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        load_error = True

if data:
    contract_id = data.get("contract_id", "")
    prev_version = data.get("prev_version", "")
    curr_version = data.get("curr_version", "")
    pipeline_status = data.get("pipeline_status", "")
    detected_changes = data.get("detected_changes", [])
    routing_decisions = data.get("routing_decisions", [])
    policy_flags = data.get("policy_flags", [])
    pipeline_metrics = data.get("pipeline_metrics", [])
    decision_pack = data.get("decision_pack", {})
else:
    contract_id = prev_version = curr_version = pipeline_status = ""
    detected_changes = routing_decisions = policy_flags = pipeline_metrics = []
    decision_pack = {}

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
left, right = st.columns([1, 2.5])

# ---------------------------------------------------------------------------
# LEFT COLUMN
# ---------------------------------------------------------------------------
with left:
    st.title("DEALta")
    st.caption(
        "Multi-agent contract review — detects changes, routes to functions, "
        "checks policy, identifies compound risks. Never approves — triages and flags."
    )
    st.divider()

    prev_contract = st.text_input(
        "Previous contract",
        value="contracts/nexus_staylink/v1_v2/nexus_staylink_v2.txt",
    )
    curr_contract = st.text_input(
        "Current contract",
        value="contracts/nexus_staylink/v2_v3/nexus_staylink_v3.txt",
    )
    prev_version_label = st.text_input("Previous version label", value="v2")
    curr_version_label = st.text_input("Current version label", value="v3")

    with st.expander("View contracts", expanded=False):
        st.markdown(f"[Previous: {prev_contract}]({prev_contract})")
        st.markdown(f"[Current: {curr_contract}]({curr_contract})")

    if st.button("Run Analysis"):
        cmd = [
            sys.executable,
            str(ROOT / "run.py"),
            "--prev-contract", prev_contract,
            "--curr-contract", curr_contract,
            "--prev-version", prev_version_label,
            "--curr-version", curr_version_label,
            "--contract-id", "nexus_staylink_001",
        ]
        with st.spinner("Running pipeline..."):
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(ROOT)
            )
        if result.returncode == 0:
            st.rerun()
        else:
            st.error(result.stderr)

    st.divider()

    if load_error:
        st.error("Pipeline output could not be loaded. Re-run.")
    elif data is None:
        st.info("Run analysis to see results")
    else:
        dp_escalations = len(decision_pack.get("escalation_items", []))
        st.metric("Contract", contract_id)
        st.caption(f"{prev_version} → {curr_version}")
        st.metric("Status", pipeline_status)
        st.metric("Changes detected", len(detected_changes))
        st.metric("Policy flags", len(policy_flags))
        st.metric("Compound risks", len(data.get("compound_risks", [])))
        st.metric("Escalation items", dp_escalations)

# ---------------------------------------------------------------------------
# RIGHT COLUMN
# ---------------------------------------------------------------------------
with right:
    if load_error:
        st.error("Pipeline output could not be loaded. Re-run.")
    elif data is None:
        st.info("Run analysis to see results")
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Decision Pack", "Function Review", "Changes",
            "Agent Findings", "Pipeline Metrics",
        ])

        # -------------------------------------------------------------------
        # TAB 1 — Decision Pack
        # -------------------------------------------------------------------
        with tab1:
            st.markdown(
                "`change_detection → invalidation → routing → "
                "policy_check → dependency → decision_pack`"
            )
            st.divider()

            rp = decision_pack.get("review_progress", {})
            overall_recommendation = decision_pack.get("overall_recommendation", "—")
            col1, col2, col3, col4 = st.columns(4)
            col1.caption("Recommendation")
            col1.markdown(status_badge(overall_recommendation), unsafe_allow_html=True)
            col2.metric("Critical issues", len(decision_pack.get("critical_issues", [])))
            col3.metric("Compound risks", len(decision_pack.get("compound_risks", [])))
            col4.metric("Functions pending", rp.get("functions_pending", "—"))

            st.divider()

            st.subheader("Summary")
            st.info(decision_pack.get("summary_narrative", "No narrative available."))

            st.subheader("Sign-off status")
            required_sign_offs = decision_pack.get("required_sign_offs", {})
            fn_cols = st.columns(3)
            for i, fn in enumerate(["Commercial", "Finance", "Legal", "Product/Tech", "Tax", "CS"]):
                status = required_sign_offs.get(fn, "NOT_REQUIRED")
                fn_cols[i % 3].caption(fn.upper())
                fn_cols[i % 3].markdown(status_badge(status), unsafe_allow_html=True)

            st.subheader("Escalation items")
            critical_issues_severity = {
                issue["change_id"]: issue.get("severity", "")
                for issue in decision_pack.get("critical_issues", [])
                if issue.get("change_id")
            }
            for item in decision_pack.get("escalation_items", []):
                cid = item.get("change_id") or "?"
                clause = item.get("clause") or "?"
                with st.expander(f"{cid} — Clause {clause}"):
                    st.caption(f"Type: {item.get('type', '')}")
                    severity = critical_issues_severity.get(cid, "")
                    if severity:
                        st.markdown(f"**Severity:** {status_badge(severity)}", unsafe_allow_html=True)
                    st.write(item.get("summary", ""))
                    st.warning(item.get("decision_needed", ""))

        # -------------------------------------------------------------------
        # TAB 2 — Function Review
        # -------------------------------------------------------------------
        with tab2:
            required_sign_offs = decision_pack.get("required_sign_offs", {})
            functions_to_show = list(dict.fromkeys(
                list(required_sign_offs.keys()) + ALL_FUNCTIONS
            ))

            for fn in functions_to_show:
                sign_off_status = required_sign_offs.get(fn, "NOT_REQUIRED")
                expanded = sign_off_status in ("REQUIRED", "INVALIDATED")

                routed = [
                    r for r in routing_decisions
                    if r.get("primary_function") == fn
                    or r.get("secondary_function") == fn
                ]
                change_ids_for_fn = [r["change_id"] for r in routed]
                fn_changes = [
                    c for c in detected_changes
                    if c["change_id"] in change_ids_for_fn
                ]
                fn_flags = [
                    f for f in policy_flags
                    if f["change_id"] in change_ids_for_fn
                ]
                fn_risks = [
                    r for r in decision_pack.get("compound_risks", [])
                    if any(cid in r.get("change_ids", []) for cid in change_ids_for_fn)
                ]

                with st.expander(f"{fn} — {sign_off_status}", expanded=expanded):
                    st.caption(f"Sign-off status: **{sign_off_status}**")

                    if not fn_changes:
                        st.caption("No changes routed for this review")
                    else:
                        st.caption("Routed changes")
                        changes_df = pd.DataFrame([
                            {
                                "change_id": c["change_id"],
                                "clause_number": c["clause_number"],
                                "clause_title": c["clause_title"],
                                "materiality_level": c["materiality_level"],
                                "v_curr_summary": c["v_curr_summary"],
                            }
                            for c in fn_changes
                        ])
                        st.dataframe(changes_df, use_container_width=True)

                        if fn_flags:
                            st.caption("Policy flags")
                            flags_df = pd.DataFrame([
                                {
                                    "change_id": f["change_id"],
                                    "rule_id": f["rule_id"],
                                    "severity": f["severity"],
                                    "explanation": f["explanation"],
                                }
                                for f in fn_flags
                            ])
                            st.dataframe(flags_df, use_container_width=True)

                        if fn_risks:
                            st.caption("Compound risks")
                            for risk in fn_risks:
                                st.write(
                                    f"{risk['risk_id']} ({risk['severity']}) — "
                                    f"{', '.join(risk['change_ids'])}"
                                )

        # -------------------------------------------------------------------
        # TAB 3 — Changes
        # -------------------------------------------------------------------
        with tab3:
            st.subheader(
                f"{len(detected_changes)} changes detected — "
                f"{prev_version} → {curr_version}"
            )

            if detected_changes:
                changes_df = pd.DataFrame([
                    {
                        "Change ID": c["change_id"],
                        "Clause": c["clause_number"],
                        "Title": c["clause_title"],
                        "Type": c["change_type"],
                        "Materiality": c["materiality_level"],
                        "Summary (current)": c["v_curr_summary"],
                    }
                    for c in detected_changes
                ])
                st.dataframe(
                    changes_df,
                    use_container_width=True,
                    column_config={
                        "Change ID": st.column_config.TextColumn("Change ID"),
                        "Clause": st.column_config.NumberColumn("Clause"),
                        "Title": st.column_config.TextColumn("Clause Title"),
                        "Type": st.column_config.TextColumn("Type"),
                        "Materiality": st.column_config.TextColumn("Materiality"),
                        "Summary (current)": st.column_config.TextColumn("Summary (current version)"),
                    },
                )
                st.caption("Colour-coded severity badges are shown in the Function Review and Agent Findings tabs.")

        # -------------------------------------------------------------------
        # TAB 4 — Agent Findings
        # -------------------------------------------------------------------
        with tab4:
            st.subheader("Compound risks")
            for risk in decision_pack.get("compound_risks", []):
                label = (
                    f"{risk['risk_id']} — {risk['severity']} — "
                    f"{', '.join(risk['change_ids'])}"
                )
                with st.expander(label):
                    st.write(risk["description"])
                    st.markdown(f"**Severity:** {status_badge(risk.get('severity', ''))}", unsafe_allow_html=True)
                    st.caption(f"Affected: {', '.join(risk['affected_functions'])}")
                    st.warning(risk["reasoning"])

            st.divider()

            st.subheader("Policy flags")
            if policy_flags:
                flags_df = pd.DataFrame([
                    {
                        "Change ID": f["change_id"],
                        "Rule ID": f["rule_id"],
                        "Rule Name": f["rule_name"],
                        "Severity": f["severity"],
                        "Explanation": f["explanation"],
                    }
                    for f in policy_flags
                ])
                st.dataframe(flags_df, use_container_width=True)

        # -------------------------------------------------------------------
        # TAB 5 — Pipeline Metrics
        # -------------------------------------------------------------------
        with tab5:
            numeric_costs = [
                m["est_cost_usd"]
                for m in pipeline_metrics
                if isinstance(m.get("est_cost_usd"), float)
            ]
            total_cost = sum(numeric_costs)
            total_time = sum(m.get("wall_time_s", 0) for m in pipeline_metrics)

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Total cost", f"${total_cost:.4f}")
            mc2.metric("Total time", f"{total_time:.0f}s")
            mc3.metric("Agents run", len(pipeline_metrics))

            st.caption("At 100 contracts/day: ~$0.24/day inference cost")

            if pipeline_metrics:
                metrics_df = pd.DataFrame([
                    {
                        "Agent": m["agent"],
                        "Time (s)": m.get("wall_time_s"),
                        "Input tokens": m.get("input_tokens"),
                        "Output tokens": m.get("output_tokens"),
                        "Cost (USD)": m.get("est_cost_usd"),
                    }
                    for m in pipeline_metrics
                ])
                st.dataframe(metrics_df, use_container_width=True)
