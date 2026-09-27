# Call-center dispute requirements

The prototype focuses on the dispute experience during and immediately after a call. Telephony, secure bank authentication, card controls, external evidence, Visa/VROL and message delivery are simulated. The working product is the dispute conversation, transaction search, classification, evidence reasoning, human handoff, case state and audit trace.

## Scope boundary

| Capability | Prototype behavior | Status |
|---|---|---|
| Call and IVR | Scripted call screen with language and reason selection | Mock |
| Customer identification | Full name plus synthetic document/customer ID matched to `customers.csv` | Mock, explicitly insecure |
| Transaction history | Read synthetic products and transactions for the identified customer | Real dataset logic |
| Conversation understanding | Extract claim, transaction clues, urgency and missing facts | Working AI component |
| Transaction matching | Rank and confirm candidate card transactions | Working code/model component |
| Dispute classification | Propose allegation and Visa family/code with confidence | Working AI component |
| Policy and evidence checks | Apply a small versioned prototype rule set | Working prototype, not production Visa eligibility |
| Card protection | Simulated block/replacement response | Mock tool |
| Visa/VROL filing | Simulated case submission and states | Mock tool |
| Merchant/acquirer evidence | Curated synthetic responses | Mock data/tool |
| Human handoff | Structured reviewer view and recorded decision | Working prototype |
| Customer updates | Generate messages and simulate delivery/status | Content is real; delivery is mocked |
| Case and audit trail | Local case state, events, versions and decisions | Working prototype |

## Functional requirements

### 1. Start the call and identify the customer

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-01 | Let the caller select or confirm a supported language and request a human | Selection follows the interaction and can be changed at any time |
| FR-02 | Use automatic language detection only as a suggestion based on multiple utterances | Low confidence, mismatch or code-switching prompts confirmation |
| FR-03 | Use accent information only to improve or evaluate transcription | Accent never identifies the customer or changes eligibility, risk or priority |
| FR-04 | Explain that the prototype uses synthetic data, mock identification and simulated external actions | Notice is visible before customer lookup |
| FR-05 | Identify a demo customer using full name plus synthetic `document_number` or `customer_id` | Both values resolve to one active customer record |
| FR-06 | Label the session `DEMO_ONLY` and restrict it to synthetic transaction lookup and mocked dispute actions | UI and audit record show method, time and scope |
| FR-07 | If identification is ambiguous or fails, route to a simulated human-assistance path without exposing another customer's data | No transaction history is returned before a unique match |

Mock identification is intentionally not secure authentication. It must never be presented as suitable for a real bank.

### 2. Retrieve and confirm the disputed transaction

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-08 | Retrieve only products where `products.customer_id` equals the identified session customer | Cross-customer access tests return no records |
| FR-09 | Limit the dispute view to `Tarjeta Crédito` and `Tarjeta Débito` products and mask `product_number` except for the last four digits | No full card number appears in UI, prompts or logs |
| FR-10 | Retrieve recent transactions using both `customer_id` and `product_id`, ordered by date | Result includes ID, date, amount, currency, merchant, channel and status |
| FR-11 | Rank candidate transactions using customer clues such as amount, date, currency and merchant text | Each candidate shows a score or explanation |
| FR-12 | Require explicit customer or human-agent confirmation of one transaction before classification or action | Case records confirmer, transaction and timestamp |
| FR-13 | Support no-match and ambiguous-match outcomes | System asks a neutral question or hands off instead of selecting silently |

The backend must derive `customer_id` from the mock session. The LLM or interface cannot submit an arbitrary customer ID to retrieve transactions.

### 3. Understand and classify the dispute

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-14 | Preserve the original customer statement and create an editable structured summary | Material fields retain transcript or data provenance |
| FR-15 | Extract allegation, authorization claim, merchant contact, expected delivery/refund, urgency and missing facts | Unsupported information remains unknown |
| FR-16 | Separate customer allegation from the proposed Visa condition | Output contains allegation, family/code candidate, confidence and alternatives |
| FR-17 | Ask the smallest neutral question that distinguishes remaining routes | Questions do not accuse the caller or presume fraud |
| FR-18 | Abstain and hand off when confidence is low, evidence conflicts or the transaction is not confirmed | No forced label below the configured threshold |
| FR-19 | Apply a versioned prototype policy to select `clarify`, `resolve`, `mock_file` or `human_review` | Decision trace records rules, evidence and missing requirements |
| FR-20 | Build a condition-specific evidence checklist with present, missing, conflicting and unavailable states | No Visa, EMV, merchant or authorization fact is fabricated |

### 4. Simulate actions without misleading the user

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-21 | Mock card block/replacement, evidence retrieval and Visa filing through controlled tools | Every response contains `mock: true` and a synthetic result ID |
| FR-22 | Represent action state as accepted, pending, completed, rejected or reconciled | Pending is never described as completed |
| FR-23 | Make mock action retries idempotent | Repeating the same request creates no second action |
| FR-24 | Clearly distinguish what the prototype actually calculated from what an external system would decide | Customer and reviewer views display the boundary |

### 5. Handoff to a human dispute specialist

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-25 | Handoff on customer request, failed identification, low confidence, poor transcription, accessibility need, conflicting evidence, mock tool failure or mandatory review | Each reason maps to a visible queue/reviewer state |
| FR-26 | Generate a summary with demo identity, confirmed language, original statement, confirmed transaction, allegation alternatives, evidence, actions, gaps and recommended next step | Reviewer can scan it without reading the full transcript |
| FR-27 | Show provenance and uncertainty for every AI-generated material field | Reviewer can inspect source text/data and confidence |
| FR-28 | Let the human correct the summary, classification and evidence state before accepting ownership | Edits, actor and reason are recorded |
| FR-29 | Explain to the customer why a human is needed and what information transfers | Customer is not asked to repeat information already captured unless clarification is necessary |

## Minimum handoff object

```json
{
  "session": {"customer_id": "CLI-...", "assurance_level": "DEMO_ONLY", "method": "NAME_AND_DOCUMENT"},
  "communication": {"confirmed_language": "es-MX", "transcript_quality": 0.88},
  "customer_statement": {"original_text": "...", "structured_summary": "..."},
  "confirmed_transaction": {"transaction_id": "TRX-...", "card_last4": "6475", "merchant": "Uber", "amount": 381.07, "currency": "USD"},
  "assessment": {"allegation": "UNAUTHORIZED_CARD", "visa_candidate": "10.4", "confidence": 0.91, "alternatives": []},
  "evidence": {"present": [], "missing": [], "conflicting": [], "mocked": []},
  "actions": [{"name": "CARD_BLOCK", "state": "COMPLETED", "mock": true}],
  "handoff": {"reason": "MANDATORY_REVIEW", "recommended_next_step": "REVIEW_10_4"}
}
```

### 6. Create the case and update the customer

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-30 | Create immutable links among mock call, customer, confirmed transaction, case and audit events | Prototype lineage completeness is 100% |
| FR-31 | End the call with case reference, current state, next step, owner and next-update time | Agent performs a concise read-back |
| FR-32 | Generate plain-language updates for case creation, evidence request, material state change, pending interval and outcome | Message matches authoritative prototype state |
| FR-33 | Simulate SMS, email, app or voice delivery using the recorded language and a masked destination | Delivery event is marked `mock: true` |
| FR-34 | Record simulated delivery success/failure and create retry work on failure | Delivery does not alter dispute outcome |
| FR-35 | Require human approval for denial, suspected misuse, policy exception or adverse outcome wording | Mandatory review cannot be bypassed |

### 7. Prevent abuse in the demo

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-36 | Scope every human and AI agent to the active mock session and case | Unrelated customer lookup is blocked |
| FR-37 | Restrict data retrieval to approved backend functions; the model cannot issue arbitrary filesystem/data queries | Prompt-injection tests cannot broaden access |
| FR-38 | Mask full document, phone, email and card values in UI, prompts and logs | Sensitive-field scan finds no unmasked full values |
| FR-39 | Require a human reason for overrides and high-impact mocked actions | Audit records actor, reason and before/after state |
| FR-40 | Log customer lookup, transaction reads, model outputs, edits, mock tools, decisions and generated messages | One trace reconstructs the end-to-end case |
| FR-41 | Support session revocation and a prototype kill switch for mock actions | Disabled tools reject new calls and preserve prior evidence |

## Nonfunctional requirements

| ID | Quality | Proposed gate |
|---|---|---|
| NFR-01 | Scope clarity | 100% of simulated external actions visibly marked as mock |
| NFR-02 | Data isolation | Zero cross-customer transactions returned in authorization tests |
| NFR-03 | Privacy | Full card/document/contact values absent from UI, prompts, summaries and logs |
| NFR-04 | Reliability | Mock actions are idempotent; every action has an authoritative local state |
| NFR-05 | Recoverability | Failed transfer/model/tool preserves case context and creates no duplicate action |
| NFR-06 | Explainability | Every classification shows evidence, gaps, alternatives, confidence and policy version |
| NFR-07 | Model quality | Macro F1 ≥0.85 and unauthorized recall ≥0.95 on an adjudicated scenario set |
| NFR-08 | Transaction matching | Top-1 ≥90%, top-3 ≥98%, and zero action on an unconfirmed transaction |
| NFR-09 | Factuality | Unsupported material facts <0.5%; 100% low-confidence cases clarify or hand off |
| NFR-10 | Language quality | Customer language can always be corrected; report detection confidence and transcript correction rate |
| NFR-11 | Fairness | Accent, country, age and segment never determine dispute rights or adverse outcomes |
| NFR-12 | Auditability | 100% of customer/transaction access and case mutations include actor, case, time, purpose and result |
| NFR-13 | Usability | Reviewer can understand the handoff without reading the full transcript in at least 90% of evaluated scenarios |
| NFR-14 | Performance | Candidate transactions and classification return within the demo latency budget; timeout falls back safely |

## Evaluation metrics for this scope

- Customer identification success/failure and ambiguous-match rate, reported only as a mock usability measure.
- Language correction and transcript correction rates.
- Transaction top-1/top-3 match and confirmation rate.
- Allegation/Visa-candidate precision, recall, calibration and abstention.
- Evidence completeness and fabricated-fact rate.
- Handoff completeness, human correction, acceptance time and repeat-story rate.
- Mock action success, duplicate action and state reconciliation.
- Case-lineage completeness, audit coverage and blocked cross-customer access.
- Status-message correctness and simulated delivery result.

Next: [[User-Stories|Call-center user stories]]
