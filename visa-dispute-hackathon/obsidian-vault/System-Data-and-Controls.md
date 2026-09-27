# System data and controls

## Component map

| Component | Role during the call | Output | Authority boundary |
|:---:|---|---|---|
| Telephony and IVR | Connect caller, capture consent, ask language and route urgency | Session, confirmed language and queue context | No identity or dispute decision |
| Mock identification service | Match full name plus synthetic document/customer ID | `DEMO_ONLY` session bound to one `customer_id` | Not secure authentication; synthetic-data access only |
| Speech and language layer | Transcribe and preserve original words | Timestamped transcript with quality signal | Agent can correct; accent never determines eligibility |
| Conversation copilot | Summarize and ask discriminating questions | Structured allegation and missing fields | Recommendation only |
| Transaction matcher | Rank candidate card transactions | Candidates with reasons | Customer or agent confirms transaction |
| Classifier | Propose allegation and Visa candidate family | Class, confidence and alternatives | Must abstain below threshold |
| Policy and evidence engine | Check deadlines, evidence and actions | Eligibility, gaps and approvals | Deterministic rules authorize |
| Tool gateway | Read and update authorized systems | Authoritative result and audit event | Least privilege, idempotency and approval |
| Human review queue | Handle ambiguity and high-risk outcomes | Approved, corrected or rejected action | Final authority for defined risk classes |
| Case and notification service | Maintain state and explain progress | Timeline, status and messages | Cannot promise unsupported outcome |
| Access and abuse controls | Scope human/AI agents to role, case and purpose | Decision, alert, revocation and audit event | Model cannot grant privilege; high-impact actions may require dual control |

## Data needed

| Data | Why it matters | Synthetic location | Gap or production action |
|:---:|---|:---:|---|
| Customer | Identity reference, country, language preference and follow-up | `customers.csv` | Authentication factors, verified language and accessibility preferences are absent |
| Card product | Instrument and available controls | `products.csv` | Card network absent; Visa is a hackathon assumption |
| Complaint | Allegation, priority, status and SLA | `complaints/**/*.csv` | Add case, origin-event and transaction links |
| Call interaction | Wait, duration, resolution and escalation | `call_center_interactions/**/*.csv` | `Queja` is not dispute-specific |
| Transcript | Original words and extraction evaluation | `call_transcripts/**/*.csv` | Availability and consent need production validation |
| Transaction | Confirm the disputed card event | `transactions/**/*.csv` | No dependable complaint link |
| Agent | Skill routing and workload | `service_agents.csv` | Add role permissions and certified skills |
| Visa and merchant evidence | Condition, evidence and network state | Not available | Mock in prototype; use licensed current rules in production |

## Minimum linked case record

- Original statement, normalized allegation, confidence and unresolved alternatives.
- Customer, product, interaction and confirmed transaction identifiers.
- Authorization claim, merchant-contact history and immediate-risk state.
- Evidence present and missing, policy version, decision trace and tool results.
- Owner, deadline, current state, next update time and communication preference.
- Selected and confirmed language, language-ID confidence, transcript quality and corrections; never infer identity from accent.
- Customer and agent assurance levels, access purpose and approval chain; never store raw authentication secrets.

## Mock identification boundary

- Full name plus synthetic `document_number` or `customer_id` must resolve to one active record.
- The session is labeled `DEMO_ONLY` and can only read that customer's synthetic products/transactions and invoke mock actions.
- The backend supplies the session `customer_id`; the LLM and interface cannot replace it.
- A failed or ambiguous match exposes no transaction history and enters a simulated human path.
- Full document, product number and contact fields remain masked. The prototype makes no authentication-security claim.

## Human handoff package

The receiving agent gets authentication assurance, confirmed language and transcription quality, original statement, confirmed transaction, allegation alternatives, urgency, actions with authoritative states, evidence and conflicts, pending dependency, owner and update promise. Every inferred field shows provenance and uncertainty. The receiving agent must accept ownership and confirm or correct the package.

## Update delivery

Use the customer's verified preferred channel and language. Send a case-created message, material state/evidence/deadline changes, the final outcome and a scheduled update when the case remains pending. Messages contain a reference, status, completed action, required action and next update, but no full card or sensitive evidence. Delivery failures create work; they do not change case state.

## Prototype versus production

| Capability | Hackathon | Production requirement |
|---|:---:|---|
| Conversation extraction | Working prototype | Consent, monitoring and validated language coverage |
| Transaction ranking | Working prototype | Live clearing and authorization data |
| Visa condition recommendation | Candidate only | Licensed current rules and specialist governance |
| Card or case action | Mock | Authenticated least-privilege APIs and approvals |
| External evidence | Mock | Visa, acquirer and merchant integrations |
| Liability or denial | Human-only scenario | Legal, policy and operational approval |

Next: [[Metrics-and-Prototype|Metrics and prototype]]
