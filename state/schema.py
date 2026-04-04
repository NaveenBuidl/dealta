#! state/schema.py

#! DEALta shared state schema
#> Single source of truth flowing through the LangGraph pipeline.
#> Every agent reads from and writes to this structure.
# If it's not in state, it doesn't exist to the system.

#! DESIGN DECISION: issue_register vs sign_offs
#> issue_register — the persistent problem tracker
# Every flagged change creates an issue. Issues survive across versions:
# they track what needs human attention, what's resolved, what's reopened.
# The memory of what needs dealing with.

#> sign_offs — the accumulated approval record
# One sign-off = one function's approval of one issue at one point in time.
# Sign-offs are NOT permanent — invalidated field is what makes the system stateful.
# Without it, stale approvals carry forward silently.
# That coordination failure is exactly what DEALta is built to prevent.

#> The relationship
# Issues accumulate in issue_register. Sign-offs attach to issues.
# New versions don't start from zero — they inherit both from all previous versions.

#! What triggers invalidation
#> DIRECT: the signed-off clause itself changed in a later version.
#> INDIRECT: a different clause changed in a way that undermines the original approval.
#
#>> Example: Finance approves commission structure in v2.
#>> v3 degrades SLA terms. Finance never reviewed SLAs —
#>> but their commission approval implicitly assumed original SLA terms held.
#>> When they don't: invalidated = True, invalidated_by_change_id recorded,
#>> issue reopens for Finance to re-review.

#! IDENTIFIER SCOPE — READ BEFORE EXTENDING THIS SCHEMA
#
# STABLE across runs (safe to use as cross-run join keys):
#   clause_number   — comes from contract text, never changes
#   rule_id         — defined in policy config, static
#
# RUN-SCOPED (only meaningful within a single pipeline run):
#   change_id       — C1, C2... assigned by change_detection LLM
#   risk_id         — CR1, CR2... assigned by dependency_check LLM  
#   issue_id        — ISS-C1... derived from change_id in run.py
#   escalation_id   — ESC-001... derived from issue_id in run.py
#
# WHY IT MATTERS:
#   The invalidation agent matches sign-offs across versions using
#   clause_number, NOT change_id. If you add a new cross-run feature,
#   anchor it to clause_number or rule_id — never to change_id.
#
# EVALS use (clause_number, rule_id) tuples as match keys for the
#   same reason — change_ids are unstable between runs.

from typing import TypedDict, Literal, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Enums (as Literals — keeps it simple without a separate enum file)
# ---------------------------------------------------------------------------

ChangeType = Literal["cosmetic", "material"]

MaterialityLevel = Literal["low", "medium", "high", "critical"]

ReviewFunction = Literal["Legal", "Commercial", "Finance", "Product/Tech", "Customer Support", "Leadership"]

IssueStatus = Literal["open", "resolved", "escalated", "reopened"]

AgentName = Literal[
    "change_detection",
    "routing",
    "policy_check",
    "dependency_check",
    "invalidation",
    "decision_pack",
]


# ---------------------------------------------------------------------------
# Sub-schemas (building blocks)
# ---------------------------------------------------------------------------

class ClauseChange(BaseModel):
    """
    One detected change between contract versions.
    Produced by the Change Detection agent.
    """
    model_config = ConfigDict(extra='forbid')

    change_id: str                          # e.g. "C1", "C2"
    clause_number: int
    clause_title: str
    change_type: ChangeType                 # cosmetic | material
    materiality_level: MaterialityLevel = "low"
    v_prev_summary: str                     # what it said before
    v_curr_summary: str                     # what it says now
    raw_v_prev: str                         # verbatim clause text, previous version
    raw_v_curr: str                         # verbatim clause text, current version
    detection_reasoning: str                # why the agent classified it this way

    @field_validator("materiality_level", mode="before")
    @classmethod
    def coerce_null_materiality(cls, v):
        # Gemini returns null for cosmetic changes; coerce to "low" before
        # the Literal constraint runs. Non-null values are validated as-is.
        return "low" if v is None else v


class RoutingDecision(TypedDict):
    """
    Which functions need to review a given change.
    Produced by the Routing agent.
    """
    change_id: str
    primary_function: Optional[ReviewFunction]
    secondary_function: Optional[ReviewFunction]
    routing_reasoning: str


class PolicyFlag(BaseModel):
    """
    A policy rule violation or flag raised against a specific change.
    Produced by the Policy Check agent.
    """
    model_config = ConfigDict(extra='forbid')

    change_id: str
    rule_id: str                            # e.g. "POL-007"
    rule_name: str                          # human-readable rule name
    flag_type: Literal["violation", "near_miss"]
    severity: MaterialityLevel
    explanation: str                        # why this change triggers the rule
    recommended_action: str                 # what the reviewer should do


class CompoundRisk(BaseModel):
    """
    A risk that only emerges from the combination of two or more changes.
    Produced by the Dependency/Consistency agent.
    The key demo moment — no single-clause review catches this.
    """
    model_config = ConfigDict(extra='forbid')

    risk_id: str                            # e.g. "CR1"
    change_ids: list[str]                   # e.g. ["C5", "C6"]
    description: str                        # what the compound risk actually is
    affected_functions: list[str]           # validated as strings; runtime values are ReviewFunction
    severity: MaterialityLevel
    reasoning: str


class Issue(TypedDict):
    """
    An item in the issue register. Created when a change is flagged.
    Updated as agents review and humans sign off.
    This is the core persistent unit — issues survive across versions.
    """
    issue_id: str                           # e.g. "ISS-001"
    source_change_id: str                   # which ClauseChange triggered this
    source_version: str                     # e.g. "v2" — which draft introduced it
    title: str
    description: str
    status: IssueStatus                     # open | resolved | escalated | reopened
    assigned_to: ReviewFunction
    policy_flags: list[PolicyFlag]
    compound_risk_id: Optional[str]         # links to CompoundRisk if applicable
    resolution_note: Optional[str]          # filled in when resolved
    resolved_in_version: Optional[str]      # e.g. "v3" — which draft resolved it
    reopened_reason: Optional[str]          # filled if a later change invalidates resolution
    created_at: str                         # ISO datetime string
    updated_at: str


class SignOff(BaseModel):
    """
    A function-level sign-off on a reviewed change or resolved issue.
    Sign-offs can be invalidated if a later version changes something
    the sign-off was based on — this is the stateful core of DEALta.
    """
    model_config = ConfigDict(extra='forbid')

    signoff_id: str
    function: ReviewFunction
    issue_id: str
    approved: bool
    conditions: Optional[str] = None       # "approved subject to X" cases
    signed_off_in_version: str             # e.g. "v2"
    invalidated: bool                      # True if a later change made this void
    invalidated_by_change_id: Optional[str] = None
    invalidated_in_version: Optional[str] = None
    timestamp: str


class EscalationItem(TypedDict):
    """
    An item that requires human decision. Produced by the Decision Pack agent.
    The system never resolves escalations — humans do.
    """
    escalation_id: str
    issue_id: str
    reason: str                             # why this can't be resolved by agents
    decision_required: str                  # plain-language ask for the human
    blocking_functions: list[ReviewFunction]
    priority: MaterialityLevel


class AgentTrace(TypedDict):
    """
    A record of what an agent did. Enables full traceability in the UI.
    Every output in the decision pack links back to one of these.
    """
    agent: AgentName
    version_processed: str
    inputs_summary: str
    outputs_summary: str
    timestamp: str


# ---------------------------------------------------------------------------
# Root state — this is what LangGraph passes between nodes
# ---------------------------------------------------------------------------

class DEALtaState(TypedDict):
    """
    The complete shared state for one contract review run.

    Design principles:
    - Version-aware from day one: prev_version + curr_version, not just "the contract"
    - Append-only lists: agents add to these, never overwrite
    - Issues are the persistent unit: they accumulate and update across versions
    - Sign-offs are invalidatable: the dependency agent can void earlier approvals
    - Agent traces are always written: every output is attributable

    This structure is what makes DEALta an orchestrator, not a summarizer.
    """

    # -- Contract identity --
    contract_id: str                        # e.g. "nexus_staylink_001"
    prev_version: str                       # e.g. "v1"
    curr_version: str                       # e.g. "v2"
    prev_contract_text: str
    curr_contract_text: str

    # -- Change Detection output --
    detected_changes: list[ClauseChange]    # all changes found, cosmetic + material

    # -- Routing output --
    routing_decisions: list[RoutingDecision]

    # -- Functional Review output --
    policy_flags: list[PolicyFlag]          # all flags across all functions

    # -- Dependency/Consistency output --
    compound_risks: list[CompoundRisk]      # cross-clause risks

    # -- Issue register (persistent across versions) --
    # This is the memory. v3 review inherits issues from v2 review.
    issue_register: list[Issue]

    # -- Sign-off tracking --
    sign_offs: list[SignOff]                # accumulates across versions

    # -- Escalations --
    escalation_items: list[EscalationItem] # items requiring human decision

    # -- Audit trail --
    agent_traces: list[AgentTrace]          # full record of agent activity

    # -- Instrumentation --
    pipeline_metrics: list[dict]            # per-agent token/cost/latency records

    # -- Decision Pack output --
    decision_pack: dict                      # assembled by the Decision Pack agent

    # -- Run metadata --
    run_id: str
    run_timestamp: str
    pipeline_status: Literal[
        "initiated",
        "change_detection_complete",
        "routing_complete",
        "functional_review_complete",
        "dependency_check_complete",
        "decision_pack_ready",
        "escalated_to_human",
    ]
