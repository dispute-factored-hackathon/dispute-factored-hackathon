# Dataset overview and data dictionary

The completely synthetic dataset covers Mexico, Colombia and Argentina from June 2023 to June 2026. Its summary describes about 19 million records across 13 tables and intentional duplicates, nulls, late arrivals and schema evolution.

| Table | Summary size | Core use |
|---|---:|---|
| `customers` | 150,000 | Country, segment and linkage |
| `products` | 400,000 | Card scope and product status |
| `transactions` | 5,000,000 | Candidate transaction search |
| `call_center_interactions` | 800,000 summary; 686,296 available | Wait, duration, resolution, follow-up and escalation |
| `call_transcripts` | 200,000 summary; 171,321 available | Original language and extraction evaluation |
| `satisfaction_surveys` | 250,000 | CSAT/NPS when linked |
| `complaints` | 80,000 summary; 67,095 available | Allegation, status, channel, priority and SLA |
| `digital_events` | 10,000,000 | Cross-channel context |
| `service_agents` | 1,200 | Skills and workload |

Report the denominator actually analyzed when summary and available-file counts differ.

## Important data and location

| Purpose | Fields | Location | Gap |
|---|---|---|---|
| Case | IDs, description, category, channel, status, priority, dates, SLA | `data/raw/complaints/year=YYYY/month=MM/day=DD/*.csv` | Generic text and missing origin link |
| Customer/card | customer, country, segment, product ID/type/status | `customers.csv`, `products.csv` | Network brand absent |
| Transaction | ID, time, amount/currency, merchant, MCC, channel, country, status | `transactions/year=YYYY/month=MM/day=DD/*.csv` | No dependable complaint link |
| Call | interaction, language/accent, duration, wait, resolution, follow-up | `call_center_interactions/.../*.csv` | Origin link empty |
| Language | transcript, entities and quality | `call_transcripts/.../*.csv` | Consent and production quality |
| Outcome | resolution, CSAT/NPS and comments | complaints, interactions and surveys | Same-case linkage required |
| Visa evidence | EMV, 3DS, authorization, delivery/refund and network state | Not supplied | Mock for prototype |

## MVP join

Join complaint to customer by `customer_id` and product by `affected_product_id`. Rank candidate transactions using customer, amount, currency, date window, merchant and channel. Require explicit confirmation. Create immutable `case_id`, `origin_event_id` and `transaction_id` links.

Never use raw PAN in analytics. Preserve missingness, provenance and late-arrival logic. Use country, age, segment and accent for evaluation slices, not liability decisions.

