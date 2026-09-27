# Visa classification and codes

The customer's words describe an **allegation**. A Visa condition is a **rule conclusion supported by evidence**. The system predicts the first and proposes the second; versioned policy and an authorized issuer workflow validate it.

| Allegation | Example | Candidate family | Next discriminator |
|---|---|---|---|
| `UNAUTHORIZED_CARD` | “I never made this purchase” | 10.x Fraud | Card present/absent, EMV facts and denial |
| `AUTHORIZATION_FAILURE` | Usually detected in records | 11.x Authorization | Exception file, decline or missing authorization |
| `PROCESSING_ERROR` | “Charged twice” | 12.x Processing | Identity, amount, currency and other-payment proof |
| `MERCHANT_DISPUTE` | “It never arrived” | 13.x Consumer | Fulfillment, cancellation, contact and refund evidence |
| `ACCOUNT_OR_DESCRIPTOR_CONFUSION` | “I do not know this name” | No code yet | Brand, subscription, household use or receipt |
| `INSUFFICIENT_INFO` | “Money disappeared” | No code yet | Ask the smallest discriminating question |

## Visa condition reference

| Family | Code | Condition | Evidence gate |
|---|---|---|---|
| Fraud, Allocation | 10.1 | EMV liability shift, counterfeit | Card-present counterfeit and EMV facts |
| | 10.2 | EMV liability shift, non-counterfeit | Applicable card-present EMV facts |
| | 10.3 | Other fraud, card present | Denial plus card-present environment |
| | 10.4 | Other fraud, card absent | Denial plus e-commerce/mail/telephone environment |
| | 10.5 | Visa Fraud Monitoring Program | Network trigger; never infer from wording |
| Authorization, Allocation | 11.1 | Card Recovery Bulletin | Exception-file evidence |
| | 11.2 | Declined authorization | Decline followed by processing |
| | 11.3 | No authorization | No valid authorization or current rule basis |
| Processing, Collaboration | 12.2 | Incorrect transaction code | Wrong debit, credit or type |
| | 12.3 | Incorrect currency | Agreed versus processed currency |
| | 12.4 | Incorrect account number | Posting/clearing evidence |
| | 12.5 | Incorrect amount | Agreed versus processed amount |
| | 12.6.1 | Duplicate processing | Same purchase processed more than once |
| | 12.6.2 | Paid by other means | Proof of alternate payment |
| | 12.7 | Invalid data | Invalid or missing required data |
| Consumer, Collaboration | 13.1 | Merchandise/services not received | Expected date passed; fulfillment checked |
| | 13.2 | Cancelled recurring transaction | Recurrence and timely cancellation |
| | 13.3 | Not as described or defective | Receipt and material defect/difference |
| | 13.4 | Counterfeit merchandise | Inauthenticity support |
| | 13.5 | Misrepresentation | Representation versus actual result |
| | 13.6 | Credit not processed | Refund agreement and absent credit |
| | 13.7 | Cancelled merchandise/services | Cancellation and unresolved charge/refund |
| | 13.8 | Original Credit Transaction not accepted | OCT payout/credit not received |
| | 13.9 | Non-receipt of cash/load value | No/partial cash or missing load |

Do not predict **12.1 Late Presentment**. The supplied workflow says Visa retired it in April 2024 and incorporated it into 11.3. Current rules and approved issuer policy remain authoritative.

Recommended MVP: 10.4, 12.6.1, 13.1, 13.2 and 13.6.

