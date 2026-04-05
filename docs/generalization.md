# DEALta — Generalisation

## The pattern

DEALta's orchestration skeleton — detect a structured delta, route it to domain-specific reviewers, check it against accumulated policy, find cross-domain compound risks, produce a human-ready decision pack — is not specific to contracts.

The same pipeline applies wherever a structured change needs multi-perspective review against accumulated context and prior decisions.

**Code review:** A PR diff routes to security, performance, and architecture reviewers. Policy check runs against dependency rules and style guides. Compound risk detection flags combinations a single reviewer would miss — a database migration coupled with an API change, or a new dependency introduced alongside a permissions change. Prior approvals (LGTM on the auth module in a previous PR) are invalidated when a later change touches the same boundary.

**PRD review:** A spec change routes to engineering, design, and legal stakeholders. Policy check tests for consistency with existing roadmap commitments. Compound risk detection surfaces conflicts between new requirements and in-flight work — a latency requirement added alongside a new third-party dependency that will increase p99. Sign-offs from the previous sprint review are invalidated when the new spec changes the acceptance criteria they were based on.

**Vendor evaluation:** A new vendor proposal routes to procurement, security, and finance. Policy check runs against vendor qualification criteria and data residency rules. Compound risk detection flags combinations — a vendor with strong security posture but contractual terms that conflict with an existing exclusivity agreement.

**Incident response triage:** A new incident signal routes to on-call engineering, SRE, and the relevant product team. Policy check runs against escalation thresholds. Compound risk detection identifies when two simultaneous signals together indicate a systemic failure that neither would indicate alone.

In each case: agents change names, policy rules change content, ground truth changes shape. The orchestration skeleton — versioned state, delta detection, multi-lens evaluation, dependency tracking, escalation logic — transfers intact.

---

## What does not generalise

Running DEALta on a software license agreement would immediately surface four gaps. This is the cleaner way to make the generalisation argument — name exactly what breaks and why.

**Policy configuration is domain-specific.** The current policy rules are calibrated to travel supplier commercial terms: commission structures, SLA P1 response time definitions, booking volume triggers, DPA requirements. A software license cares about IP assignment, source code escrow, indemnification caps, and audit rights. None of those exist in the current `policy/rules.json`. Porting requires rewriting policy config, not touching agent code.

**Compound risk ground truth is domain-specific.** The planted compound risks assume a specific clause dependency pattern — rate changes interacting with volume commitments interacting with SLA penalties. Software licensing risk clusters look different (IP assignment interacting with indemnification scope, audit rights interacting with liability caps). The eval suite would need new ground truth before the dependency agent could be trusted on a new contract type.

**Materiality thresholds are company-specific.** What counts as a critical change at Nexus (a 50% credit facility reduction, a P1 SLA degradation from 4 to 8 hours) reflects one company's commercial risk tolerance. A different company reviewing the same clause changes might classify them differently. Materiality calibration is configuration, but it requires domain expertise to set correctly.

**Eval keying assumes stable clause structure.** The eval system keys on clause numbers as stable identifiers — they come from the contract text and do not change between runs. Contracts without numbered clauses, or with nested sub-sections and lettered clauses, break this assumption. A different stable anchor (clause title hash, positional identifier) would be needed before the eval system would work reliably.

---

## The architectural point

The distinction matters because it determines where porting effort goes. If the architecture did not generalise, porting DEALta to a new domain would require redesigning agents, rethinking state schema, and rebuilding orchestration logic. That is an architecture problem — expensive and risky.

Because the architecture does generalise, porting is a configuration and evaluation problem: rewrite `policy/rules.json`, define new ground truth for the target domain, calibrate materiality thresholds, confirm eval keying works for the new document structure. That work is meaningful but bounded. It does not require touching agent code, state schema, or graph structure.

This is the same principle behind any well-designed platform: the hard work of getting the orchestration layer right pays forward to every domain that runs on top of it.
