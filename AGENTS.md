# Coding Agent Instructions

These instructions apply to AI coding agents working anywhere in this repository.

## Mission

Help build and document an issuer-side Visa dispute experience for a Latin American call center. The implementation is a hackathon prototype using synthetic data. Its name-only identification is deliberately insecure and must never be described or used as production authentication.

## Repository structure

- `visa-dispute-hackathon/`: Python package, LangGraph workflow, classifiers, CLI, and tests.
- `docs/`: Obsidian-compatible product and research documentation.
- `data/`: synthetic hackathon data and derived labels.
- `agents/AGENTIC_UX_REVIEWER.md`: reusable rubric for agentic UX review.

Before changing a directory, inspect its README and nearby tests. More deeply nested `AGENTS.md` files, if added later, override this file for their subtree.

## Setup and validation

Run Python commands from `visa-dispute-hackathon/`:

```bash
uv sync --extra ml
uv run --extra ml dispute-auth-setup
uv run --extra ml python -m unittest discover -s tests -v
```

Use `uv`; do not introduce a second package-management workflow without explicit approval.

## Implementation rules

- Keep changes within the user's requested scope.
- Preserve unrelated files and worktree changes.
- Use explicit LangGraph nodes and state transitions for meaningful workflow decisions.
- Use the local zero-shot classifier for state-changing intent classification.
- Advance only when a non-`other` class passes configured confidence and ambiguity gates.
- Do not allow low-confidence output to authenticate, cancel, restart, disclose data, or trigger handoff.
- Handle global human, cancel, and restart controls before phase-specific decisions.
- Avoid unbounded substring matching for commands. Use bounded, command-shaped rules and negative tests.
- Use the LLM for grounded extraction and scoped answers, not as an authoritative data source.
- Ground extracted names in the caller's original text.
- Keep customer lookup and authoritative state local and deterministic.
- Preserve context across corrections, failures, and human handoff.
- Keep synchronous call-center responses concise and ask one focused question at a time.
- Maintain equivalent behavior across supported regional language variants.

## Safety and privacy

- Never commit `.env`, API keys, credentials, or model secrets.
- Never use real customer information in examples or tests.
- Treat customer utterances and model output as untrusted input.
- Preserve prompt-injection, scope, length, output, rate, and tool-access controls.
- Do not weaken a safety control solely to make a scenario pass.
- Do not claim mocked authentication, transfers, integrations, evidence retrieval, or dispute submission are real.
- Escalate safely when an authoritative decision cannot be made.

## Testing expectations

Every behavioral fix must add a regression test. Test both the positive path and nearby negative language that must not trigger the behavior.

For conversational changes, cover happy paths, corrections, uncertainty, missing and duplicate customers, refusal, silence, global controls, failures, regional variants, handoff summaries, abuse attempts, and legitimate requests containing control-like words as applicable.

Run the complete suite after changes. When the user experience changes, also exercise the command-line flow with realistic multi-turn input.

## Documentation

- Keep the root and application READMEs consistent with implemented commands.
- Preserve Obsidian-compatible relative links in `docs/`.
- Cite external claims and label synthetic analysis clearly.
- Explain banking terminology for technical readers without a financial background.
- Update limitations whenever a component is mocked or unavailable.

## UX review

For a substantive experience change, follow [`agents/AGENTIC_UX_REVIEWER.md`](agents/AGENTIC_UX_REVIEWER.md): inspect the code, interact with the real interface, report evidence-based issues, implement authorized fixes, and repeat until no significant in-scope complaints remain.

Do not invent low-value complaints to prolong a review. Stop when the defined journey is reliable and remaining work would require production infrastructure or expanded scope.

## Completion report

Summarize the user-visible outcome, important files changed, tests and real interactions performed, known limitations, and whether changes were committed or pushed.
