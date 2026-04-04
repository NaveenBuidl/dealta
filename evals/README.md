# DEALta — Eval Suite

## Philosophy

Ground truth is written before building agents, not retrofitted after. Every agent has a defined expected output before any code is touched. Evals are the specification, not the validation.

## Structure

| Script | What it tests | Method | Score |
|---|---|---|---|
| `eval_change_detection.py` | Change detection agent — did it find the right clauses? | Deterministic — precision/recall vs ground truth | 100% |
| `eval_routing.py` | Routing agent — did it send changes to the right functions? | Deterministic — exact match vs ground truth | 89% (known issue — see below) |
| `eval_policy.py` | Policy check agent — did it flag the right rules? | Deterministic — clause + rule_id match vs ground truth | 100% |
| `eval_compound_risk.py` | Dependency agent — did it detect cross-clause compound risks? | Deterministic — planted risk match vs ground truth | 3/3 planted risks |
| `eval_invalidation.py` | Invalidation agent — did it correctly reopen v2 sign-offs? | Deterministic — 5 checks including true negatives | 5/5 |
| `eval_decision_pack.py` | Decision Pack agent — recommendation, escalation items, structure | Deterministic — field-level match vs ground truth | 6/6 |
| `eval_llm_judge.py` | Decision Pack narrative — is generated text faithful to structured findings? | LLM-as-judge — OpenAI gpt-4o-mini judges Gemini output | PASS |

## Two eval methods — why both

**Deterministic evals** check structured outputs: clause numbers, severity levels, routing assignments, boolean flags. A Python script compares agent output to ground truth JSON. Binary correct/incorrect. Used for every agent except narrative generation.

**LLM-as-judge** checks generated text. The `summary_narrative` in the Decision Pack is free text — there is no exact string to match against. A second LLM (different provider from the generator) reads the narrative alongside the structured findings and judges faithfulness. Different provider = different training = avoids correlated blind spots. One criterion, binary PASS/FAIL output.

## Known issues

**Routing eval at 89%:** Root cause is in change detection, not routing. The change detection agent merges Clauses 12 and 13 into a single change in some runs, which means routing receives one item where ground truth expects two. The routing logic itself is correct — it routes whatever it receives accurately. Explainable, not fixing.

**Compound risk — agent finds more than ground truth plants:** Ground truth plants 3 compound risks. The agent sometimes identifies a 4th legitimate risk not in ground truth. Eval checks only planted risks. Extra finds are not penalised.

## Eval methodology reference

Amazon three-layer eval framework (Feb 2026). Offline ground truth evals as regression tests → online LLM-as-judge on sampled production outputs → production failures feed back into eval set. Eval is a loop, not a phase.
