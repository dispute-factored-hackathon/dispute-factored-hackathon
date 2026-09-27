# Customer personas

These personas describe customer jobs and failure modes, not demographic stereotypes. A caller can move between personas as evidence changes. Country, age and segment may support coverage testing but must not determine eligibility, liability or adverse treatment.

## Persona map

| Persona | Primary job | Starting statement | Highest design risk |
|:---:|---|---|---|
| **1. Alarmed cardholder** | Protect the account and report a charge that may be unauthorized | “I do not recognize this purchase” | Delay while credentials or money may still be at risk |
| **2. Uncertain recognizer** | Identify the transaction before deciding whether to dispute it | “I do not know what this merchant name means” | Opening the wrong case or blocking a valid card |
| **3. Persistent resolver** | Correct an improper charge or missing refund after prior effort | “I already cancelled or contacted the merchant” | Repeated storytelling and no visible ownership |
| **4. Assisted caller** | Complete the process with clear human guidance | “Please explain what I need to do” | Exclusion caused by language, access or digital confidence |

## Persona 1  Alarmed cardholder

**Archetype:** urgent protection seeker  
**Constructed quote:** “I do not recognize this purchase. Is my card still safe?”

| Persona canvas | Description |
|---|---|
| Context | Sees a transaction that may be unauthorized and wants to stop further harm |
| Goals | Confirm what happened, protect the card or credentials, understand access to funds and receive a case number |
| Behaviors | Calls quickly, may speak under stress and searches the statement during the conversation |
| Pains | Waiting during possible active misuse, repeating sensitive details, unclear provisional treatment and technical terms |
| Success | Risk questions first, confirmed action, clear scope and a case with status and next update |
| Evidence | 1,374 card call-center proxy cases carry the `Cargo no reconocido` label |
| Hypothesis to validate | Immediate reassurance and a clear separation between protection and reimbursement improve trust |

## Persona 2  Uncertain recognizer

**Archetype:** transaction identification seeker  
**Constructed quote:** “The name on my statement means nothing to me.”

| Persona canvas | Description |
|---|---|
| Context | Unsure whether the charge is fraud, a subscription, family use or an unfamiliar merchant descriptor |
| Goals | Understand the merchant and decide whether to continue without unnecessary card replacement |
| Behaviors | Provides an approximate date and amount, checks receipts and changes the assessment as context appears |
| Pains | Opaque descriptors, too many transactions and pressure to label the event as fraud |
| Success | A privacy-safe candidate list, transaction confirmation and a clean stop when the purchase is recognized |
| Evidence | The synthetic dataset has no dependable complaint-to-transaction key |
| Hypothesis to validate | Merchant normalization and ranked candidates reduce false claims and unnecessary card replacement |

## Persona 3  Persistent resolver

**Archetype:** outcome and ownership seeker  
**Constructed quote:** “I already cancelled this and I am calling again.”

| Persona canvas | Description |
|---|---|
| Context | Recognizes the merchant but disputes a recurring, duplicate, wrong-amount or unrefunded charge |
| Goals | Avoid repeating the story, submit existing evidence and know the owner and deadline |
| Behaviors | Refers to prior calls, dates and merchant promises and may request escalation |
| Pains | Scattered evidence, invisible progress, restarted intake and network terminology |
| Success | One case timeline with evidence gaps, owner, deadline, updates and an understandable appeal path |
| Evidence | 1,451 proxy cases carry the `Cobro indebido` label; 14.51% are marked repeat complainers |
| Hypothesis to validate | Case continuity and proactive status reduce avoidable repeat calls |

## Persona 4  Assisted caller

**Archetype:** guided access seeker  
**Constructed quote:** “Please stay with me and explain each step.”

| Persona canvas | Description |
|---|---|
| Context | Needs human guidance because of language, accessibility, connectivity, digital confidence or complexity |
| Goals | Authenticate safely and complete the essential process without being forced to another channel |
| Behaviors | Requests repetition, uses verbal guidance and benefits from teach-back confirmation |
| Pains | Fast scripts, jargon, inaccessible links, poor transcription and context loss after transfer |
| Success | Adapted pace and language, phone completion, teach-back and accessible follow-up |
| Evidence | Broad complaint callers span ages 21 to 84; synthetic accent labels differ in 18.67% of populated pairs |
| Hypothesis to validate | Adaptive scripts and editable real-time summaries reduce cognitive load without reducing rights |

Next: [Value Proposition Canvases](Value-Proposition-Canvases.md)

