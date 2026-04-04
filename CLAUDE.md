# DEALta -- Contract Review Orchestrator

Multi-agent system that detects contract changes, routes them to business functions, checks policy compliance, identifies compound risks, and produces escalation-ready decision packs. Built with LangGraph, Gemini 2.5 Flash, Python.

## Project structure

```
agents/           -- one file per agent (change_detection, routing, policy_check, dependency)
orchestrator/     -- LangGraph graph definition (graph.py)
state/            -- shared state schema (schema.py) -- single source of truth
contracts/        -- synthetic test contracts + ground truth
evals/            -- per-agent eval scripts scored against ground truth
policy/           -- structured policy rules (rules.json)
config.py         -- model selection, provider fallback logic
run.py            -- full pipeline entry point, saves pipeline_output.json
test_quota.py     -- check Gemini model availability before sessions
```

## Architecture

Linear pipeline: Change Detection -> Routing -> Policy Check -> Dependency Check -> (Decision Pack -- not yet built)

All agents read from and write to a single typed state object (DEALtaState in state/schema.py). Nothing passes between agents outside state. If it is not in state, it does not exist to the system.

## Model configuration

All agents use `generate_with_fallback()` from config.py. Default provider is Gemini with a fallback chain. Do not hardcode model names in agent files.

Current fallback order: gemini-2.5-flash -> gemini-2.5-pro -> gemini-2.5-flash-lite -> gemini-2.0-flash -> gemini-2.0-flash-lite

OpenAI (gpt-4o) is available as backup. Switch by changing PROVIDER in config.py.

Run `python test_quota.py` at session start to check which models have quota.

## Eval methodology

Ground truth is defined when test data is created, not after agents are built. Each agent has its own eval script in evals/ that scores against ground_truth.json.

- Change Detection: 100% precision, 100% recall, 100% type accuracy
- Routing: 89% primary function accuracy (C12/C13 merge — known, documented)
- Policy Check: 100% detection rate
- Dependency/Compound Risk: 3/3 (gpt-4o), confirmed 2/2 previously with Gemini
- Stateful Tracking: 8/8

To run evals:
```bash
cd code
python evals/eval_change_detection.py
python evals/eval_routing.py
python evals/eval_policy_check.py
python evals/eval_dependency.py pipeline_output.json
```

To run the full pipeline:
```bash
cd code
python run.py
```

## Key design decisions

- Agents have narrow jobs. If a flag is wrong, you need to know which agent produced it. Separation is for traceability, debugging, and evaluation.
- Compound risk detection is the differentiator. A compound risk must satisfy: "Neither change creates this risk alone, but together they create X." If you cannot complete that sentence, it is not a compound risk.
- Individually flagged changes can still participate in compound risks. The Session 4 CR2 failure was caused by the agent treating "do not duplicate policy flags" as a reason to exclude C4 from compound risk participation. That is a category error. Compound risk logic is independent of policy flag status.
- State schema is version-aware from day one. SignOff.invalidated is the key concept for cross-version tracking (Level 5/6 work, not yet built).

## What is built vs what is next

Built and evaluated: Change Detection, Routing, Policy Check, Dependency/Compound Risk agent, LangGraph pipeline wired end-to-end.

Next: Level 5 (stateful v2->v3 tracking), Level 6 (compound risk refinement), Level 7 (Decision Pack agent + Streamlit demo UI).

## Conventions

- Commit after each working state, not just at session end
- Agent prompts use SYSTEM_PROMPT constant + a build function for the user message
- All agents return the full state dict with their additions, not just their output
- JSON parsing: strip markdown fences, then json.loads
- No em dashes in README or public-facing copy
