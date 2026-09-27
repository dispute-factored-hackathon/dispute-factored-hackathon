# System data and controls

## Component map

| Component | Role during the call | Output | Authority boundary |
|:---:|---|---|---|
| Telephony and IVR | Connect caller, capture consent and route urgency | Authenticated session and queue context | No dispute decision |
| Speech and language layer | Transcribe and preserve original words | Timestamped transcript with quality signal | Agent can correct; accent never determines eligibility |
| Conversation copilot | Summarize and ask discriminating questions | Structured allegation and missing fields | Recommendation only |
| Transaction matcher | Rank candidate card transactions | Candidates with reasons | Customer or agent confirms transaction |
| Classifier | Propose allegation and Visa candidate family | Class, confidence and alternatives | Must abstain below threshold |
| Policy and evidence engine | Check deadlines, evidence and actions | Eligibility, gaps and approvals | Deterministic rules authorize |
| Tool gateway | Read and update authorized systems | Authoritative result and audit event | Least privilege, idempotency and approval |
| Human review queue | Handle ambiguity and high-risk outcomes | Approved, corrected or rejected action | Final authority for defined risk classes |
| Case and notification service | Maintain state and explain progress | Timeline, status and messages | Cannot promise unsupported outcome |

## Data needed

| Data | Why it matters | Synthetic location | Gap or production action |
|:---:|---|:---:|---|
| Customer | Authentication, country, language and follow-up | `customers.csv` | Add verified language and accessibility preferences |
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

## Prototype versus production

| Capability | Hackathon | Production requirement |
|---|:---:|---|
| Conversation extraction | Working prototype | Consent, monitoring and validated language coverage |
| Transaction ranking | Working prototype | Live clearing and authorization data |
| Visa condition recommendation | Candidate only | Licensed current rules and specialist governance |
| Card or case action | Mock | Authenticated least-privilege APIs and approvals |
| External evidence | Mock | Visa, acquirer and merchant integrations |
| Liability or denial | Human-only scenario | Legal, policy and operational approval |

Next: [Metrics and prototype](Metrics-and-Prototype.md)

