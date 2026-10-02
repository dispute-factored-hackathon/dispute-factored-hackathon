# Classifier technology decision

## Decision

Use the existing OpenAI integration as a schema-constrained LLM classifier. One raw customer turn produces one validated object with language, intent, confidence, abuse class, abuse confidence, extracted name, and an optional grounded answer.

This replaces the local Hugging Face zero-shot pipeline, separate language model, label-to-enum adapters, probability-map handling, model-download command, and platform-specific Torch dependencies.

## Alternatives researched

| Option | Raw text | JSON Schema | Immediate fit | Decision |
|---|---:|---:|---:|---|
| Jev | Yes | Typed decision API | Access was reported as unavailable to the team; its public ecosystem and endpoints are also still evolving | Revisit when stable access is available |
| OpenAI Structured Outputs | Yes | Strict schema adherence with native Pydantic helpers | Already configured, credited, and integrated through LangChain | Selected |
| Google Gemini structured outputs | Yes | Supports JSON Schema and Pydantic, including structured classification | Technically viable but adds a provider, credentials, dependency, and operational path without solving a current gap | Valid fallback, not selected |
| Cloudflare Workers AI JSON mode | Yes | Accepts a schema, but its documentation says adherence is not guaranteed in extreme cases | Adds another account and requires extra validation/retry handling | Not selected |
| Conventional local zero-shot models | Yes | Requires label mapping and application-side confidence/probability handling | Already caused large Torch/Transformers dependencies and platform-specific installation problems | Removed |

## Why OpenAI was selected

OpenAI Structured Outputs constrain the response to the supplied schema and provide native Pydantic integration. This gives the project the Jev-like property it needs—turning unstructured customer language into a typed decision—without another provider or preprocessing pipeline. Schema adherence does not guarantee semantic correctness, so the application still applies confidence thresholds, deterministic customer lookup, grounded-name validation, fixed safety responses, retry limits, and human handoff.

## Sources

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Google Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Cloudflare Workers AI JSON mode](https://developers.cloudflare.com/workers-ai/features/json-mode/)
- [Jev API repository](https://github.com/jev-ai/jev-api)

Sources reviewed on 2026-09-27.
