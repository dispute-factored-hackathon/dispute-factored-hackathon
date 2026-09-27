# Agentic Visa dispute resolution for the call center

This wiki gives engineers, product teams, mentors and judges one shared model for an issuer-side Visa card dispute experience through the call-center channel.

## Scope

- Credit and debit card complaints labeled `Cargo no reconocido` or `Cobro indebido` in the supplied synthetic dataset.
- All cards are treated as Visa for the hackathon because the dataset has no network field.
- The prototype can interpret customer language, find a candidate transaction, apply versioned rules, assemble evidence, mock actions and support human review.
- The prototype cannot file a real Visa dispute, block a real card or determine legal liability.

## Main design decision

The system assists the agent during the call and makes uncertainty visible. An LLM may interpret and summarize. Code may rank transactions. Tools may retrieve or update authorized systems. Versioned rules authorize eligible actions. Humans approve ambiguous, adverse, high-risk or irreversible outcomes.

## Read the wiki

| Topic | What it provides |
|---|---|
| [Problem and baseline](Problem-and-Baseline.md) | Dataset evidence, channel rationale and design implications |
| [Customer personas](Customer-Personas.md) | Four behavior-based caller archetypes and persona canvases |
| [Value Proposition Canvases](Value-Proposition-Canvases.md) | Customer jobs, pains and gains mapped to product capabilities |
| [Current call-center journey](Current-Call-Center-Journey.md) | Current customer journey and operational friction |
| [Future journey with agentic AI](Future-Journey-with-Agentic-AI.md) | Redesigned journey, agent roles and human controls |
| [System data and controls](System-Data-and-Controls.md) | Components, data sources, authority boundaries and mocks |
| [Metrics and prototype](Metrics-and-Prototype.md) | Pilot gates, requirements and demonstration scenarios |
| [Glossary and limitations](Glossary-and-Limitations.md) | Banking vocabulary, analytical definitions and evidence limits |

## Evidence status

Quantitative baselines come from the complete supplied synthetic dataset. Personas and quotes are constructed design tools, not real customers or research findings. Proposed targets are pilot gates, not achieved outcomes.

