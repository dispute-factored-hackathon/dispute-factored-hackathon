# Current call-center journey

The current journey is reconstructed from dataset fields and issuer workflow. It is a service-design model, not an observed ethnographic study.

```mermaid
flowchart LR
    A[1 Notice problem] --> B[2 Decide to call]
    B --> C[3 IVR and wait]
    C --> D[4 Authenticate]
    D --> E[5 Tell the story]
    E --> F[6 Find transaction]
    F --> G[7 Classify and protect]
    G --> H[8 Create or transfer case]
    H --> I[9 Wait for investigation]
    I --> J[10 Receive outcome]
```

## Journey map

| Stage | Customer action and question | Frontstage experience | Backstage work | Friction and risk |
|:---:|---|---|---|---|
| 1  Notice problem | Reviews statement or alert | No bank interaction yet | Transaction and authorization records exist separately | Descriptor ambiguity creates anxiety or a false fraud assumption |
| 2  Decide to call | Looks for the number and may contact the merchant | Chooses channel based on urgency and confidence | No case or structured allegation | Customer does not know which evidence to prepare |
| 3  IVR and wait | Navigates menus and waits | Broad routing category | Queue and routing logic | Urgent protection and ordinary follow-up can share a queue |
| 4  Authenticate | Answers identity questions | Repeats known data | Agent validates identity and access | Time and accessibility burden |
| 5  Tell the story | Explains the event in natural language | Agent listens and notes | Recording may exist, transcript may not | Meaning is compressed and the story may be repeated |
| 6  Find transaction | Searches amount, date and merchant | Agent asks for clues | No dependable complaint-to-transaction key | Wrong match undermines later decisions |
| 7  Classify and protect | Answers whether they made or authorized it | Agent selects route and may block or replace card | Claim, evidence, Visa condition and policy must be separated | Binary questions can confuse fraud, scam and commercial dispute |
| 8  Create or transfer case | Provides evidence and receives a reference | Hold or specialist transfer | Operations receives case | Origin interaction is not linked in supplied complaint records |
| 9  Wait for investigation | Wants status, money and deadline | Limited or manual updates | Operations gathers evidence and tracks workflow state | Vague status can drive repeat calls |
| 10  Receive outcome | Accepts, questions or appeals | Explanation may arrive elsewhere | Issuer records resolution and closure | Technical language and incomplete evidence reduce trust |

## Moments that matter

- **Before transaction confirmation:** preserve uncertainty and avoid premature accusation or irreversible action.
- **Before protective action:** show the authority, scope and verified result.
- **Before case submission:** confirm transaction, allegation, evidence and missing fields.
- **Before the call ends:** state owner, current status, next step and next update time.

Next: [Future journey with agentic AI](Future-Journey-with-Agentic-AI.md)

