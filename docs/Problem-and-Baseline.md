# Problem and baseline

The call center is the largest intake channel in the card dispute proxy. It combines customer urgency with fragmented evidence and weak linkage between the conversation, the transaction and the complaint record.

## Baseline from the synthetic dataset

| Signal | Value | Interpretation |
|---|---:|---|
| Card dispute proxy entering through call center | **2,825 of 5,605 (50.40%)** | The channel deserves first-class workflow support |
| Broad inbound phone calls categorized as complaints | **82,261 (17.11% of inbound calls)** | Broad complaint workload, not a dispute-only metric |
| Average wait for broad complaint calls | **120 seconds** | Delay occurs before downstream investigation begins |
| Average call duration for broad complaint calls | **435 seconds** | About 7.25 minutes of conversation after waiting |
| Broad complaint calls marked resolved during interaction | **43.74%** | More than half are not marked resolved during the call |
| Broad complaint calls requiring follow-up | **62.81%** | Follow-up is the normal path in the snapshot |
| Card dispute proxy with SLA breach | **20.11%** | One in five carries an operational breach signal |
| Median populated resolution time in card call-center proxy | **16 days** | Customers need truthful status and expectations |
| Card call-center complaint linked to origin interaction | **0.00%** | The conversation cannot be traced to the case with available linkage |

## What the dataset reveals

- The card call-center proxy contains 1,451 `Cobro indebido` and 1,374 `Cargo no reconocido` complaints.
- Credit cards account for 1,997 proxy cases and debit cards for 828.
- The country mix is Mexico 1,406, Colombia 898 and Argentina 521. This reflects the synthetic dataset design and is not market prevalence.
- Only 66.38% of the two dispute-intake labels have an affected product.
- No dependable key links a complaint to its transaction.
- Only 24.99% of broad phone complaint records indicate transcript availability, although every record indicates a recording.

## Design implications

1. Preserve the caller's original words before translating them into structured fields or a Visa candidate code.
2. Make transaction matching part of the call.
3. Require the customer or agent to confirm the exact transaction before dispute routing.
4. Create immutable links between interaction, transcript, case, customer, product and transaction.
5. Separate immediate protection from later liability and chargeback decisions.
6. Provide proactive status because investigation and follow-up extend beyond the call.

## Population definitions

- **Card dispute proxy:** complaints with subcategory `Cargo no reconocido` or `Cobro indebido` linked to `Tarjeta Crédito` or `Tarjeta Débito`.
- **Card call-center proxy:** card dispute proxy with `reception_channel = Call Center`.
- **Broad complaint call:** inbound phone interaction with `contact_reason = Queja` or `reason_category = Queja`. It includes complaints beyond card disputes.

Next: [[Customer-Personas|Customer personas]]

