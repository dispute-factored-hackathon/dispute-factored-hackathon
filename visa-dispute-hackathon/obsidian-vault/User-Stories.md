# Call-center dispute user stories

These stories cover the working dispute experience. Identification, telephony, external issuer actions, Visa/VROL and message delivery are mocked.

## Start and identify

### US-01 P0 Choose the conversation language

**As a caller, I want to select and correct my language so that I can explain the dispute clearly.**

- Explicit customer choice overrides automatic detection.
- Low-confidence or mixed-language speech triggers confirmation.
- Accent is used only to improve/evaluate transcription, never identity or eligibility.

### US-02 P0 Enter the synthetic demo safely

**As a demo caller, I want to provide my full name and synthetic document/customer ID so that the prototype can find my synthetic transactions.**

- Both fields resolve to one active customer.
- Session displays `DEMO_ONLY` and `NAME_AND_DOCUMENT`.
- Failure or ambiguity exposes no transactions and moves to mock human assistance.
- Prototype states that this is identification, not secure bank authentication.

### US-03 P0 Keep one customer's data isolated

**As a project owner, I want the session customer to be fixed by the backend so that the LLM cannot access another customer's transactions.**

- Backend derives `customer_id` from the mock session.
- Arbitrary IDs from prompts or interface are ignored or rejected.
- All products and transactions are checked against the session customer.

## Find the transaction

### US-04 P0 See recent card activity

**As a caller, I want to review my synthetic card transactions so that I can identify the disputed purchase.**

- Only credit/debit-card products for the mock customer are included.
- Full product number is masked; date, amount, currency, merchant, channel and status are shown.
- Results are ordered by date and can be narrowed by clues.

### US-05 P0 Confirm the exact transaction

**As a caller, I want the system to rank likely transactions so that the dispute does not target the wrong purchase.**

- Candidate explanations use amount, date, currency and merchant clues.
- Ambiguous or empty results trigger clarification or handoff.
- Explicit confirmation is required and audited.

### US-06 P0 Recognize a legitimate purchase

**As a caller who did not recognize a descriptor, I want merchant context so that I can stop the process if the purchase is mine.**

- Show only allowed synthetic merchant context.
- Stop without creating a dispute or mock block when customer recognizes it.

## Understand and classify

### US-07 P0 Tell the story once

**As a caller, I want my original explanation preserved and summarized so that I do not repeat it.**

- Original text and editable summary remain linked.
- Summary separates customer statement, dataset fact and model inference.
- Low transcription quality is visible.

### US-08 P0 Receive a supported classification

**As a call-center agent, I want an allegation and Visa candidate with evidence and uncertainty so that I ask the right next question.**

- Allegation and Visa condition are separate.
- Display confidence, alternatives, supporting facts, conflicts and gaps.
- Low confidence abstains and hands off.

### US-09 P0 Build an evidence checklist

**As a dispute specialist, I want to know which evidence exists, is missing or is mocked.**

- Each item has state, source and freshness.
- External authorization, EMV, merchant and Visa evidence is explicitly mocked/unavailable.
- No absent fact is invented.

## Simulate actions and hand off

### US-10 P0 Demonstrate the next banking action

**As a judge, I want to see how card protection or Visa filing would be orchestrated without believing that a real external action occurred.**

- Tool response contains `mock: true` and synthetic result ID.
- Accepted, pending, completed, rejected and reconciled states are distinct.
- Retrying the same action is idempotent.

### US-11 P0 Receive a useful human handoff

**As a dispute specialist, I want a concise case package so that I can continue without rereading the full conversation.**

- Include mock identity, language, original statement, confirmed transaction, classification alternatives, evidence, actions, gaps and recommendation.
- Exclude full card/document/contact values.
- Show provenance and uncertainty for AI-generated fields.
- Human can correct and accept ownership.

### US-12 P0 Understand why a human is joining

**As a caller, I want to know why the system is handing me to a person and what information follows me.**

- Explain the reason and what transfers.
- Do not ask for a full repeat unless clarification is necessary.
- Failed transfer preserves context and creates a simulated reconnect path.

### US-13 P1 Review adverse or ambiguous cases

**As a reviewer, I want to approve denial, suspected misuse, conflicts and exceptions rather than let the model decide them.**

- Mandatory cases cannot bypass review.
- Reviewer sees sources, policy version and previous edits/actions.
- Decision, correction and reason are audited.

## Case and updates

### US-14 P0 End with a clear case state

**As a caller, I want a reference, current state, owner, next step and update time before the interaction ends.**

- Case links call, customer and confirmed transaction.
- Read-back distinguishes real prototype state from mocked external state.
- Pending is never described as complete.

### US-15 P1 Preview proactive updates

**As a caller, I want clear updates in my chosen language so that I know what the bank would communicate next.**

- Generate messages for case creation, evidence request, state/deadline change, pending interval and outcome.
- Mask sensitive details and avoid unsupported promises.
- Simulated delivery is explicitly marked mock and records success/failure.

## Governance

### US-16 P0 Prevent agent access outside the case

**As a customer and security reviewer, I want human and AI agents limited to the active synthetic case.**

- Model can call only approved retrieval/action functions.
- Cross-customer lookup, arbitrary paths, bulk browsing and unapproved exports are blocked.
- Full card, document and contact values are masked.

### US-17 P1 Audit the complete dispute journey

**As an auditor, I want one trace showing what the customer said, what data was read, what the model proposed, what the human changed and which mock actions ran.**

- Reads, model outputs, policy decisions, human edits, tool calls and generated messages are logged.
- Every event includes actor, purpose, case, time, version and result.
- Audit access is itself restricted.

### US-18 P2 Evaluate dispute quality rather than fake business impact

**As a product owner, I want metrics for the components we actually built so that the demo makes credible claims.**

- Report transaction matching, classification, abstention, evidence completeness, handoff quality, state correctness and audit coverage.
- Report synthetic dataset baselines only as context.
- Do not claim real authentication security, real Visa filing, real card protection, real notification delivery or causal savings.

## End-to-end demo

1. Caller chooses Spanish and sees the synthetic-data/mock notice.
2. Caller supplies full name plus synthetic document/customer ID; session becomes `DEMO_ONLY`.
3. Backend retrieves only that customer's masked credit/debit-card transactions.
4. Caller describes an unrecognized card-not-present purchase and confirms a ranked transaction.
5. System proposes `UNAUTHORIZED_CARD` and Visa 10.4 with evidence gaps and alternatives.
6. A mock card-control tool returns a visible simulated state.
7. Human reviewer receives the structured handoff, corrects or accepts it and records a decision.
8. Prototype creates a linked case and generates a mocked status message in the confirmed language.
9. Audit trace shows data access, model/rule versions, human edits and mock tool states.

Next: [[Metrics-and-Prototype|Metrics and prototype]]
