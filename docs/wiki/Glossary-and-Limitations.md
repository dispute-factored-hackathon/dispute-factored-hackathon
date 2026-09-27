# Glossary and limitations

## Banking vocabulary

| Term | Plain-language definition |
|---|---|
| Cardholder | Customer whose card was used or appears on the transaction |
| Issuer | Bank or financial institution that issued the card and owns the customer relationship |
| Acquirer | Institution that serves the merchant and carries merchant-side evidence |
| Visa | Card network that defines the dispute workflow and network rules |
| Merchant | Business that accepted the payment and may refund or contest it |
| Dispute | Formal request to investigate or reverse a transaction |
| Fraud | Unauthorized use or deception; the customer statement is an allegation until evidence is evaluated |
| Refund | Money voluntarily returned by the merchant |
| Chargeback | Network reversal when the applicable rules permit it; it is not a synonym for refund or dispute |
| Provisional credit | Temporary customer credit while an investigation continues; not a final outcome |

## Dispute labels used by the solution

| Class | Meaning |
|---|---|
| `UNAUTHORIZED` | Customer says they did not perform or approve the transaction |
| `SCAM_AUTHORIZED` | Customer approved a payment after deception |
| `COMMERCIAL_DISPUTE` | Customer recognizes the merchant but disputes delivery, service, cancellation or refund |
| `PAYMENT_ERROR` | Duplicate, wrong amount, pending, failed or another operational error |
| `FIRST_PARTY_MISUSE` | Valid customer disputes a valid transaction through confusion, family use or possible misuse; never accuse automatically |
| `NOT_A_DISPUTE` | Informational or service issue without a transaction allegation |
| `INSUFFICIENT_INFO` | Available language cannot support a safe classification |

## Evidence limitations

- The dataset is synthetic and cannot establish real prevalence, financial loss or causal impact.
- No dependable key links complaints to transactions.
- The card call-center proxy has no populated origin-interaction link.
- The dataset has no card-network field. Treating every card as Visa is a project assumption.
- Personas are constructed archetypes and require interviews, call listening and accessibility research.
- Visa, acquirer, merchant, authorization and regulatory systems are unavailable and must be mocked.

## Safe language

- Customer language describes an **allegation**, not a proven cause or liability decision.
- A model **recommends**; versioned rules and authorized people decide.
- A tool action must report **success**, **failure** or **pending**. The interface must not imply completion before confirmation.
- A charge may become recognized during the call; the workflow must support a safe stop.

Return to [Home](Home.md).

