# Contributing

Thank you for contributing to the Dispute Factored Hackathon project. The repository combines research, product design, synthetic banking data, and a Python agent prototype. Changes should preserve both technical correctness and a clear call-center experience.

## Before starting

1. Read the root [`README.md`](README.md).
2. For application changes, read [`visa-dispute-hackathon/README.md`](visa-dispute-hackathon/README.md).
3. For agent-experience changes, use [`agents/AGENTIC_UX_REVIEWER.md`](agents/AGENTIC_UX_REVIEWER.md) as the review rubric.
4. If you are using a coding agent, follow [`AGENTS.md`](AGENTS.md).

## Development setup

```bash
cd visa-dispute-hackathon
cp .env.example .env
uv sync --extra ml
uv run --extra ml dispute-auth-setup
```

Add your own project-scoped OpenAI key to `.env` only when testing the interactive application. Never commit the file or expose the key in logs, screenshots, issues, or pull requests.

## Making a change

- Keep each change focused on one problem or coherent feature.
- Preserve existing user data and unrelated worktree changes.
- Prefer explicit graph states, schemas, and deterministic validation over prompt-only behavior.
- Treat model output as untrusted and probabilistic.
- Require confidence checks before model classifications alter consequential state.
- Preserve correction, cancellation, restart, and human handoff.
- Keep multilingual behavior equivalent across supported locales.
- Use synthetic data in tests and examples.
- Update documentation when behavior, setup, configuration, or limitations change.

## Testing requirements

Run the complete suite from `visa-dispute-hackathon/`:

```bash
uv run --extra ml python -m unittest discover -s tests -v
```

Every bug fix should include a regression test with the original reproduction. For conversation changes, test the intended utterance, an ambiguous variation, a semantically similar negative example, relevant languages, and state or handoff-summary integrity.

When practical, exercise the repaired flow through the actual command-line interface as well as automated tests.

## Documentation changes

The `docs/` directory is an Obsidian-compatible vault. Preserve relative links and keep [`docs/Home.md`](docs/Home.md) and [`docs/Navigation.md`](docs/Navigation.md) consistent when adding or renaming major pages.

Research claims must include a traceable source. Clearly distinguish external evidence, synthetic-dataset analysis, assumptions, and mocked behavior.

## Pull requests

A pull request should include:

- the user or engineering problem;
- implemented behavior and important design decisions;
- tests performed and their results;
- screenshots or transcripts when the experience changed;
- security, privacy, data, or compatibility implications;
- remaining limitations or intentionally deferred work.

Do not include secrets, real customer information, model caches, virtual environments, or unrelated files.

## Definition of done

A change is ready when the primary scenario works end to end, failures have recovery paths, state-changing decisions are validated, the full test suite passes, user-facing text is regionally appropriate, documentation is current, and the diff contains no credentials or sensitive data.

## Conduct

Be respectful, specific, and evidence-based. Review the work rather than the person. Explain banking and AI terminology so contributors from either discipline can participate effectively.
