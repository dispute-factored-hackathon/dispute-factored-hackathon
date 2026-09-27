# Complaint categories and classifier taxonomy

`Cargo no reconocido` and `Cobro indebido` are structured complaint subcategories, not free text and not final Visa classifications.

| Subcategory | Count | Share of 67,095 | Intake meaning |
|---|---:|---:|---|
| `Cargo no reconocido` | 12,297 | 18.33% | Customer does not recognize a charge |
| `Cobro indebido` | 12,194 | 18.17% | Charge is said to be incorrect or improper |
| Combined proxy | 24,491 | 36.50% | Requires product and transaction triage |

`Problema con app` has 12,128 records and is another prominent category. Charts must show the complete distribution rather than presenting the two dispute labels as the whole complaint population.

## Cross-payment taxonomy

| Code | Meaning | Example |
|---|---|---|
| `UNAUTHORIZED` | Customer did not perform or approve payment | “I did not make this purchase” |
| `SCAM_AUTHORIZED` | Customer approved after deception | “I thought it was the bank” |
| `COMMERCIAL_DISPUTE` | Recognized merchant; delivery/service/refund issue | “I cancelled and was not refunded” |
| `PAYMENT_ERROR` | Operational error | “They charged me twice” |
| `FIRST_PARTY_MISUSE` | Confusion, family use or possible misuse | “I forgot the subscription” |
| `NOT_A_DISPUTE` | Informational/service issue | “How do I see my limit?” |
| `INSUFFICIENT_INFO` | Unsafe to choose a route | “Money disappeared” |

## Required structured output

```json
{"allegation":"PROCESSING_ERROR","visa_condition_candidate":"12.6.1","confidence":0.94,"supporting":["same_card","same_merchant","same_amount","same_day"],"missing":["transaction_identity_confirmation"],"status":"VISA_CODE_PENDING_EVIDENCE","next_question":"Did you make two separate purchases for this amount?","workflow":"COLLABORATION"}
```

Separate allegation from conclusion, confirm the transaction, preserve alternatives, abstain below threshold and require human review before denial, suspected misuse or an irreversible action.
