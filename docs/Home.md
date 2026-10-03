# Agentic Visa dispute resolution for the call center

This wiki is the shared knowledge base for the Factored AI and Data Hackathon project. It explains the banking problem in plain language, records what the synthetic dataset shows, maps the issuer workflow and defines the proposed agentic system.

## Project scope

- The team represents the **card issuer**, the bank that serves the cardholder.
- The product focuses on **Visa credit- and debit-card disputes received through the call center**.
- Every linked card is treated as Visa because the dataset has no network field.
- External bank, merchant, acquirer and Visa services are mocked. The prototype does not move real money, block a real card or file a real dispute.

## Topic map

| Area | Pages |
|---|---|
| Understand the problem | [[Disputes-Fraud-Refunds-and-Chargebacks|Definitions]] · [[Economic-Impact-of-Payment-Disputes|Economic impact]] · [[LATAM-Impact-and-Payment-Methods|LATAM context]] |
| Understand the ecosystem | [[Stakeholders-and-Responsibilities|Stakeholders]] · [[Visa-Classification-and-Codes|Visa classification]] · [[Visa-Issuer-Dispute-Lifecycle|Visa lifecycle]] |
| Understand the evidence | [[Dataset-Overview-and-Data-Dictionary|Dataset overview]] · [[Problem-and-Baseline|Problem and baseline]] · [[Complaint-Categories-and-Classifier-Taxonomy|Complaint taxonomy]] |
| Design the experience | [[Customer-Personas|Personas]] · [[Value-Proposition-Canvases|Value Proposition Canvases]] · [[Current-Call-Center-Journey|Current journey]] · [[Future-Journey-with-Agentic-AI|Future journey]] |
| Build and evaluate | [[System-Data-and-Controls|System and data]] · [[Functional-and-Nonfunctional-Requirements|Requirements]] · [[Metrics-and-Prototype|Metrics]] · [[User-Stories|User stories]] · [[PostgreSQL-and-DuckDB-Partner-Deployment|Database deployment handoff]] |
| Check assumptions | [[Glossary-and-Limitations|Glossary]] · [[Research-Sources|Research sources]] · [[Project-Document-Index|Document index]] |

## Evidence labels

| Label | Meaning |
|---|---|
| **Synthetic-data finding** | Calculated from the hackathon data; not national prevalence |
| **External evidence** | Published research or official data linked in the source page |
| **Product decision** | A team choice, such as treating every card as Visa |
| **Hypothesis or target** | A proposed design or acceptance gate still requiring validation |

## Headline synthetic baseline

- **24,491 of 67,095 complaints (36.50%)** are `Cargo no reconocido` or `Cobro indebido`.
- **5,605** of those records link to credit- or debit-card products.
- **2,825 of 5,605 (50.40%)** enter through the call center.
- The card-linked proxy has **20.62% SLA breach**, **70.40% open or in process**, and **14.81% repeat complainants**.
- The dataset has **no reliable complaint-to-transaction link** and **0% populated complaint-to-origin-interaction linkage**.

These are intake signals, not confirmed fraud, chargebacks or Visa codes.

## Main product decision

The system assists the agent and exposes uncertainty. An LLM interprets customer language. Code ranks transactions. A classifier proposes an allegation and Visa family. Versioned rules validate eligibility. Tools return authoritative states. A human approves ambiguous, adverse, high-risk or irreversible outcomes.

Quantitative baselines come from the supplied synthetic dataset. Personas are constructed design tools, and proposed targets are not achieved outcomes.
