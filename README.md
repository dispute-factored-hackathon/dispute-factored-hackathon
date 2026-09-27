# Dispute Factored Hackathon

An issuer-side prototype for improving Visa card-dispute intake in Latin American call centers with agentic AI.

The implementation focuses on identifying a synthetic customer, understanding natural-language responses, answering scoped dispute questions, preserving conversation state, and handing the interaction to a person when automation should not proceed.

> [!WARNING]
> Authentication by name is intentionally mocked for the hackathon. It is not secure and must never protect real banking data or be represented as production authentication.

## What the prototype demonstrates

- LangGraph-based conversation orchestration
- Grounded full-name extraction and scoped conversational answers with an OpenAI model
- Local multilingual zero-shot classification for state-changing decisions
- Accent-insensitive customer lookup against synthetic data
- Brazilian Portuguese, American English, and regional Spanish experiences
- Explicit confirmation before mocked authentication succeeds
- Global human-handoff, cancel, and restart controls
- Confidence gates that prevent uncertain classifications from advancing state
- Context-preserving handoff summaries for call-center agents
- Input, output, scope, and model-usage controls

## Repository map

| Path | Purpose |
|---|---|
| [`visa-dispute-hackathon/`](visa-dispute-hackathon/) | Python application, tests, and runtime configuration |
| [`docs/`](docs/README.md) | Obsidian-compatible research and product documentation |
| [`data/`](data/) | Synthetic hackathon data and classifier labels |
| [`agents/AGENTIC_UX_REVIEWER.md`](agents/AGENTIC_UX_REVIEWER.md) | Tool-agnostic agent definition for iterative UX reviews |
| [`AGENTS.md`](AGENTS.md) | Instructions for coding agents working in this repository |
| [`CONTRIBUTE.md`](CONTRIBUTE.md) | Contribution workflow and quality requirements |

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- An OpenAI API key for interactive LLM extraction and scoped answers

## Set up the project

```bash
git clone https://github.com/dispute-factored-hackathon/dispute-factored-hackathon.git
cd dispute-factored-hackathon/visa-dispute-hackathon
cp .env.example .env
```

Add a project-scoped key to `.env`:

```dotenv
OPENAI_API_KEY=your-project-key
OPENAI_AGENT_MODEL=gpt-4.1-mini
MAX_LLM_CALLS_PER_SESSION=20
```

Install the application and prepare the local models:

```bash
uv sync --extra ml
uv run --extra ml dispute-auth-setup
```

Never commit `.env` or a real API key.

## Run the demo

From `visa-dispute-hackathon/`:

```bash
uv run --extra ml dispute-auth-demo \
  --customers ../data/raw/customers.csv \
  --country-code +55 \
  --language auto
```

Use the small fixture when the complete synthetic dataset is unavailable:

```bash
uv run --extra ml dispute-auth-demo \
  --customers tests/fixtures/customers.csv \
  --country-code +55 \
  --language pt
```

Fixture examples include `Ana Silva` for a unique match, `Nobody Here` for no match, and `Alex Santos` for an ambiguous duplicate.

## Run the tests

```bash
cd visa-dispute-hackathon
uv run --extra ml python -m unittest discover -s tests -v
```

The automated suite uses controlled model doubles and does not consume OpenAI API credits. Some integration tests use the complete synthetic database when available.

## Documentation

Open [`docs/`](docs/README.md) as an Obsidian vault and begin with [`Home.md`](docs/Home.md). It covers the dispute problem, stakeholders, Visa classification, dataset baselines, personas, journeys, requirements, metrics, architecture, controls, limitations, and research sources.

The implementation-specific guide is available in [`visa-dispute-hackathon/README.md`](visa-dispute-hackathon/README.md).

## Safety and scope

- Use only synthetic or explicitly authorized test data.
- Treat model output as probabilistic, not authoritative.
- Keep consequential transitions behind deterministic validation, confidence thresholds, and human review where appropriate.
- Do not weaken abuse controls to make a test pass.
- Do not claim that mocked services, transfers, authentication, or third-party integrations are real.

## Contributing

Read [`CONTRIBUTE.md`](CONTRIBUTE.md) before opening a change. AI coding agents must also follow [`AGENTS.md`](AGENTS.md).

## License

This project is available under the [MIT License](LICENSE).
