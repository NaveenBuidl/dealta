import argparse
import json
from datetime import datetime, timezone

import config
from langfuse.types import TraceContext
from orchestrator.graph import build_graph, build_graph_skip_detection
from state.schema import DEALtaState


def load_contract(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_prev_signoffs(path: str) -> list:
    with open(path) as f:
        prev = json.load(f)
    sign_offs = prev.get("sign_offs", [])
    print(f"[run] Loaded {len(sign_offs)} sign-off(s) from {path}")
    return sign_offs


parser = argparse.ArgumentParser()
parser.add_argument("--prev-contract", default="contracts/nexus_staylink/v1_v2/nexus_staylink_v1.txt")
parser.add_argument("--curr-contract", default="contracts/nexus_staylink/v1_v2/nexus_staylink_v2.txt")
parser.add_argument("--prev-output", default=None, help="Path to previous pipeline output JSON (for stateful runs)")
parser.add_argument("--prev-version", default="v1")
parser.add_argument("--curr-version", default="v2")
parser.add_argument("--contract-id", default="nexus_staylink_001")
parser.add_argument("--output", default=None, help="Output path (default: outputs/pipeline_output_{contract_id}_{curr_version}.json)")
parser.add_argument("--skip-detection", action="store_true", help="Skip change detection and reuse cached results")
args = parser.parse_args()

if args.output is None:
    if args.contract_id and args.curr_version:
        args.output = f"outputs/pipeline_output_{args.contract_id}_{args.curr_version}.json"
    else:
        args.output = "outputs/pipeline_output_latest.json"

prev_text = load_contract(args.prev_contract)
curr_text = load_contract(args.curr_contract)

sign_offs = []
if args.prev_output:
    sign_offs = load_prev_signoffs(args.prev_output)

detected_changes = []
if args.skip_detection:
    cached_path = args.output
    with open(cached_path) as f:
        saved = json.load(f)
    detected_changes = saved.get("detected_changes", [])
    print(f"[change_detection] Skipped — loaded {len(detected_changes)} changes from {cached_path}")
    graph = build_graph_skip_detection()
else:
    graph = build_graph()

initial_state: DEALtaState = {
    "contract_id": args.contract_id,
    "prev_version": args.prev_version,
    "curr_version": args.curr_version,
    "prev_contract_text": prev_text,
    "curr_contract_text": curr_text,
    "detected_changes": detected_changes,
    "routing_decisions": [],
    "policy_flags": [],
    "agent_traces": [],
    "pipeline_status": "initiated",
    "compound_risks": [],
    "issue_register": [],
    "sign_offs": sign_offs,
    "escalation_items": [],
    "decision_pack": {},
    "run_id": "run_001",
    "run_timestamp": datetime.now(timezone.utc).isoformat(),
    "pipeline_metrics": [],
}

def print_metrics(metrics):
    print("\n" + "="*60)
    print(f"{'Agent':<25}{'Time(s)':<10}{'In Tok':<10}{'Out Tok':<10}Cost($)")
    print("-"*60)
    for m in metrics:
        print(f"{m['agent']:<25}{m['wall_time_s']:<10}{m['input_tokens']:<10}{m['output_tokens']:<10}{m['est_cost_usd']}")
    total = sum(m['est_cost_usd'] for m in metrics if isinstance(m['est_cost_usd'], float))
    print("-"*60)
    print(f"{'TOTAL':<45}{round(total,6)}")
    print("="*60)


def generate_escalation_items(result: dict) -> list:
    escalations = []
    for flag in result.get("policy_flags", []):
        if flag.get("severity") == "critical" or flag.get("flag_type") == "violation":
            escalations.append({
                "escalation_id": f"ESC-{len(escalations)+1:03d}",
                "issue_id": f"ISS-{flag['change_id']}",
                "reason": flag["explanation"],
                "decision_required": flag["recommended_action"],
                "blocking_functions": [
                    r["primary_function"]
                    for r in result.get("routing_decisions", [])
                    if r["change_id"] == flag["change_id"]
                ],
                "priority": flag["severity"]
            })
    return escalations

print(f"\n[run] {args.contract_id}: {args.prev_version} → {args.curr_version}")
config.current_trace_id = config.langfuse.create_trace_id()
config.current_trace = config.langfuse.start_observation(
    trace_context=TraceContext(trace_id=config.current_trace_id),
    name="dealta-pipeline-run",
    as_type="span",
    input={
        "contract_id": args.contract_id,
        "prev_version": args.prev_version,
        "curr_version": args.curr_version,
        "run_id": "run_001",
    },
    metadata={
        "tags": [args.contract_id, f"{args.prev_version}_to_{args.curr_version}"],
    },
)
result = graph.invoke(initial_state)

dp = result.get("decision_pack", {})
config.current_trace.update(
    output={
        "overall_recommendation": dp.get("overall_recommendation"),
        "changes_detected": len(result.get("detected_changes", [])),
        "policy_flags": len(result.get("policy_flags", [])),
        "compound_risks": len(result.get("compound_risks", [])),
        "invalidated_signoffs": sum(1 for s in result.get("sign_offs", []) if s.get("invalidated")),
        "agent_summaries": [
            {"agent": t["agent"], "output": t["outputs_summary"]}
            for t in result.get("agent_traces", [])
        ],
    }
)
config.current_trace.end()
config.langfuse.flush()

result["escalation_items"] = generate_escalation_items(result)
print_metrics(result.get("pipeline_metrics", []))

print("\n=== PIPELINE COMPLETE ===")
print(f"Contract : {args.contract_id}  ({args.prev_version} → {args.curr_version})")
print(f"Status   : {result['pipeline_status']}")
print(f"Changes detected: {len(result['detected_changes'])}")
print(f"Routing decisions: {len(result['routing_decisions'])}")
print(f"Policy flags: {len(result['policy_flags'])}")
print(f"Agent traces: {len(result['agent_traces'])}")
print(f"Compound risks: {len(result['compound_risks'])}")
print(f"Sign-offs: {len(result['sign_offs'])} ({sum(1 for s in result['sign_offs'] if s.get('invalidated'))} invalidated)")
print(f"Escalation items: {len(result['escalation_items'])}")

with open(args.output, "w") as f:
    json.dump(result, f, indent=2, default=str)
print(f"Output saved to {args.output}")