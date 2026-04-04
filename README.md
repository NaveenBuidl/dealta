# DEALta

DEALta is a multi-agent contract review orchestrator. I built DEALta to solve a workflow problem I encountered while negotiating a supplier agreement across six internal teams at a B2B travel platform. The contract went through multiple revision rounds with a major accommodation supplier, coordinated across Legal, Finance, Tax, Commercial, Customer Support, and Product/Tech.

## The problem

Once a contract goes through multiple rounds across Legal, Finance, Commercial, Product, and CS, the work stops being just "review the draft." The real problem becomes coordination.

Nobody has a clean view of what changed, what actually matters, who needs to look at it, or whether a new edit in v3 breaks an assumption Finance already signed off on in v2.

Most of that work still happens in email threads and spreadsheets. The contract owner ends up chasing reviews, reconstructing history, and trying not to miss something important. Things get missed, not because people are careless, but because the workflow is brittle.

That is the gap DEALta is built for.

## What it does

You give DEALta two contract versions. It returns:

- the clauses that changed, with a view on whether the change is cosmetic or material
- the internal team that should review each material change, with reasoning
- policy violations or near-misses tied to structured internal rules
- cross-clause combinations that create risk no single reviewer would catch alone
- the items that need explicit human sign-off before the deal can move forward

It also tracks state across negotiation rounds. When v3 arrives, the system does not start from zero. It knows what was flagged in v2, what was resolved, what was signed off, and what has been reopened by a later change.

It does not approve contracts. The point is to triage, route, and surface risk. A human still makes the decision.

## Why this is split into agents

Each agent has a narrow job.

| Agent | What it does |
|---|---|
| Change Detection | Compares two versions clause by clause and separates rewording from real change |
| Routing | Decides which internal function owns each material change |
| Policy Check | Tests changes against structured internal policy rules |
| Dependency Check | in progress |
| Decision Pack | in progress |

I could have forced this through one large prompt, but that would make failures hard to inspect. If a flag is wrong, I need to know where it came from. The separation is there for traceability, debugging, and evaluation.

## Where it came from

This project comes from a real negotiation problem.

While negotiating a supplier agreement at a B2B travel platform, the hardest part was not the deal discussion itself. It was keeping track of what changed across rounds and spotting when one edit quietly affected something another team had already reviewed.

A good example was an SLA change in a later round that altered an assumption tied to the commission structure. Finance had effectively reviewed that area already, but the dependency was easy to miss because the tooling did not surface it.

DEALta is built to catch that kind of failure.

## Architecture

```text
v1 + v2 contract texts
        |
[ Change Detection ]
  Clause-level diff
  Cosmetic vs material
  Materiality: low / medium / high / critical
        |
[ Routing ]
  Primary + secondary function per change
  Legal / Finance / Commercial / Product/Tech / CS / Leadership
        |
[ Policy Check ]
  Violation or near-miss per change
  Recommended action per flag
        |
[ Dependency Check ]
  Compound risk detection
  Cross-clause invalidation
  Issue reopening
        |
[ Decision Pack ]
  Escalation-ready output
  Sign-off matrix
  Full agent traceability
```

The workflow is orchestrated with LangGraph. All agents write to and read from one typed state object. Nothing moves between agents outside that state.

## State schema

This is what makes it more than a contract summariser. The shared state tracks:

```python
detected_changes       # what changed and how material it is
routing_decisions      # who needs to review what
policy_flags           # what violates internal rules
compound_risks         # cross-clause risk pairs
issue_register         # open issues across rounds
sign_offs              # accumulated approvals
reopened_issues        # closed issues invalidated by later changes
escalation_items       # what needs a human decision
decision_history       # record across versions
agent_traces           # which agent did what and when
```

If each new draft is treated as a fresh start, the system loses most of its value.

## Eval approach

The eval setup is defined when the test data is created, not after the fact. The synthetic contracts include planted changes with known classifications, known policy violations, and known compound risks. Each agent is scored on its own before the full workflow is wired together.

Current scores on the v1 to v2 `nexus_staylink` test case:

| Agent | Metric | Score |
|---|---|---|
| Change Detection | Precision | 100% |
| Change Detection | Recall | 100% |
| Change Detection | Type accuracy | 100% |
| Routing | Primary function accuracy | 89% |
| Policy Check | Detection rate | 100% |

## Build status

| Session | Status | Output |
|---|---|---|
| 0 | Done | Repo, state schema, synthetic contracts, ground truth |
| 1 | Done | Change Detection agent, eval passing |
| 2 | Done | Routing and Policy Check agents, evals passing |
| 3 | Next | LangGraph pipeline wired end to end |
| 4 | Planned | Dependency agent, compound risk detection |
| 5 | Planned | Decision Pack and Streamlit trace view |

## Running it locally

```bash
git clone https://github.com/NaveenBuidl/dealta-contract-orchestrator
cd dealta-contract-orchestrator/code

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# add your GEMINI_API_KEY to .env

python evals/eval_change_detection.py
python evals/eval_routing.py
python evals/eval_policy_check.py
```

Requires Python 3.11 or newer. Uses Gemini 2.5 Flash.

## What this is not

DEALta is not a contract summariser. If it only summarises, it is not doing the job.

It is not a CLM tool either. CLM systems handle authoring, approvals, and storage. DEALta sits in the gap between "a new draft arrived" and "the right people have reviewed the right changes."

It is also not an approval system. It surfaces what needs a decision and keeps the review state coherent. A human still signs off.


## Build log
Session-by-session progress, design decisions, and what broke:
https://www.notion.so/Project-DEALta-Working-Doc-3314095d09518087a344fd8541370a7b?source=copy_link