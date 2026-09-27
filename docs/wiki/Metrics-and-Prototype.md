# Metrics and prototype

Targets below are pilot gates, not achieved improvements. Compare matched cohorts by country, product, claim family, priority and intake period.

## Measures

| Layer | Measure | Synthetic baseline | Pilot gate |
|:---:|---|:---:|---|
| Customer | Status and next-step comprehension | Not available | At least 85% explain both in a post-call test |
| Customer | Same-case repeat contact within 14 days | Linkage unavailable | Create linkage, then reduce 20% relative without worse outcomes |
| Call center | Broad complaint-call wait | Mean 120 sec | Do not worsen matched queue wait; report p50, p90 and abandonment |
| Call center | Broad complaint-call duration | Mean 435 sec | Reduce clerical time 10% after quality gate |
| Workflow | Card dispute SLA breach | 20.11% | At most 15% after matched baseline validation |
| Workflow | Origin interaction linkage | 0.00% | 100% of prototype cases link interaction and transaction |
| Model | Unauthorized and commercial-dispute recall | No ground truth | At least 90% on adjudicated evaluation set |
| Model | Calibration and abstention | No ground truth | Low confidence always clarifies or routes to a person |
| Safety | Unsafe irreversible action without authority | Not available | Zero in evaluated scenarios |
| Operations | Duplicate tool action | Not available | Zero through idempotency |
| Fairness | Outcome and error gaps | Not available | No unexplained material gap across relevant slices |

## Prototype scenarios

| Scenario | Persona | What the demo proves |
|---|:---:|---|
| Unrecognized card-not-present purchase | Alarmed cardholder | Urgency detection, confirmation, mock protection, 10.4 candidate and human review |
| Ambiguous descriptor that becomes recognized | Uncertain recognizer | Candidate ranking, safe stop and no unnecessary dispute |
| Cancelled subscription with missing refund | Persistent resolver | Evidence checklist, candidate route, deadline and continuity |
| Low-confidence speech or accessibility need | Assisted caller | Correction, clarification, alternate path and no forced decision |
| Tool timeout or contradictory evidence | All personas | Explicit failure state, no duplicate action and controlled handoff |

## Functional requirements

- Preserve the original narrative with consent and quality indicators.
- Rank transactions and require confirmation before routing.
- Return class, confidence, missing fields, alternatives and recommended route.
- Apply versioned rules and evidence gates before action.
- Support agent correction, human review, audit, continuity and proactive status.

## Nonfunctional requirements

- **Security and privacy:** least privilege, encryption, minimization and retention controls.
- **Reliability:** idempotent actions, explicit pending states, retries and rollback where possible.
- **Accessibility:** language support, screen-reader compatibility and alternate verification.
- **Observability:** trace IDs, model and rule versions, latency, errors and overrides.
- **Performance:** responsive suggestions with safe degradation when a dependency fails.

## Decision gates

- Do not automate until an adjudicated evaluation set and human fallback exist.
- Do not claim business improvement without matched cohorts and same-case contact linkage.
- Do not use sentiment, accent, age or segment for eligibility, liability or adverse treatment.
- Stop rollout if safety, fairness or comprehension worsens even when handling time improves.

Next: [Glossary and limitations](Glossary-and-Limitations.md)

