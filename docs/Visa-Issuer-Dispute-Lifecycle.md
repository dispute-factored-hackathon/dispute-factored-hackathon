# Visa issuer dispute lifecycle

## Triage and code selection

```mermaid
flowchart TD
 C["[Cardholder]:<br/>Describe the problem"]:::customer --> I["[Issuer support]:<br/>Authenticate and preserve language"]:::issuer
 I --> D["[Data]:<br/>Authorization, clearing, descriptor and receipt"]:::data
 I --> T["[Tool]:<br/>Search and rank transactions"]:::tool
 D --> Q{"[Issuer]:<br/>Transaction confirmed?"}:::branch
 T --> Q
 Q -- No/unclear --> C2["[Cardholder]:<br/>Answer smallest clarifying question"]:::customer
 C2 --> T
 Q -- Yes --> R{"[Issuer]:<br/>Immediate credential risk?"}:::branch
 R -- Yes --> P["[Tool]:<br/>Apply approved reversible protection"]:::tool
 R -- No --> M["[Model]:<br/>Classify allegation and propose Visa family"]:::label
 P --> M
 M --> E{"[Policy engine]:<br/>Evidence complete and eligible?"}:::branch
 E -- Missing --> C2
 E -- Review --> H["[Issuer reviewer]:<br/>Review ambiguity, denial or high risk"]:::issuer
 E -- Eligible --> O["[Issuer operations]:<br/>Resolve, file or escalate"]:::issuer
 classDef customer fill:#ffd9d9,stroke:#b42318,color:#7a271a;
 classDef issuer fill:#dbeafe,stroke:#175cd3,color:#102a56;
 classDef label fill:#173f73,stroke:#0b2f59,color:#fff;
 classDef tool fill:#dcfae6,stroke:#079455,color:#054f31;
 classDef data fill:#fef0c7,stroke:#dc6803,color:#7a2e0e;
 classDef branch fill:#eaecf0,stroke:#667085,color:#101828;
```

## After validation

```mermaid
flowchart TD
 D["[Data]:<br/>Evidence, policy version and deadline"]:::data --> O["[Issuer operations]:<br/>Create case and start timers"]:::issuer
 O --> P{"[Policy engine]:<br/>Pre-dispute route appropriate?"}:::branch
 P -- Yes --> T["[Tool/Visa service]:<br/>Use approved inquiry route"]:::tool
 P -- No --> V["[Tool/VROL]:<br/>Submit condition and evidence"]:::tool
 T --> Q{"[Issuer]:<br/>Authoritative financial resolution?"}:::branch
 Q -- No --> V
 V --> A["[Acquirer/merchant]:<br/>Accept or respond with evidence"]:::external
 A --> R{"[Issuer reviewer]:<br/>Does response rebut the dispute?"}:::branch
 R -- No --> E["[Issuer reviewer]:<br/>Continue only if policy permits"]:::issuer
 R -- Yes --> X["[Issuer operations]:<br/>Accept and reconcile"]:::issuer
 E --> C["[Cardholder]:<br/>Receive status, outcome and appeal"]:::customer
 X --> C
 C --> L["[Data/audit]:<br/>Record evidence, decision, action and money"]:::data
 classDef customer fill:#ffd9d9,stroke:#b42318,color:#7a271a;
 classDef issuer fill:#dbeafe,stroke:#175cd3,color:#102a56;
 classDef tool fill:#dcfae6,stroke:#079455,color:#054f31;
 classDef data fill:#fef0c7,stroke:#dc6803,color:#7a2e0e;
 classDef external fill:#ede9fe,stroke:#7f56d9,color:#3e1c96;
 classDef branch fill:#eaecf0,stroke:#667085,color:#101828;
```

| Failure | Consequence | Control |
|---|---|---|
| Unrecognized descriptor immediately coded as fraud | False report and unnecessary replacement | Merchant recognition and neutral clarification |
| LLM chooses code from language alone | Invalid condition | Allegation model plus deterministic eligibility |
| Wrong transaction | Harm and invalid filing | Ranked candidates plus confirmation |
| Missing evidence | Rework and missed deadline | Code-specific checklist |
| API acceptance treated as completion | False assurance | Explicit accepted/pending/completed/reconciled states |
| Automated denial or misuse allegation | Conduct and fairness risk | Mandatory human review and appeal |

