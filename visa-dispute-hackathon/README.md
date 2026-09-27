# Dispute Factored Hackathon

Issuer-side Visa dispute resolution for the call-center channel.

Project documentation is maintained in the repository's [`docs`](../docs/README.md) directory. Open that directory as an Obsidian vault and start with `Home`.

## Mock customer identification

The first implemented layer asks for the caller's language and full name. A local language-identification model detects English, Portuguese or Spanish from natural caller speech. A separate local multilingual intent classifier categorizes the response as `provides_name`, `avoids_answer`, `asks_why`, `requests_human` or `other`. When a name is embedded in a sentence—such as `meu nome é Samuel Andrés Díaz Pérez`—a local LLM extracts the name before the normalized database lookup.

The default classifier is [`MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`](https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli), an MIT-licensed multilingual zero-shot model. It runs locally after the model files are downloaded.

Language identification uses [`langid.py`](https://github.com/saffsd/langid.py), a pretrained statistical model supporting 97 languages. It is restricted here to English (`en`), Portuguese (`pt`) and Spanish (`es`), returns normalized confidence scores and runs fully offline. Explicit menu choices remain deterministic; free-form utterances use this model with a minimum-confidence threshold.

Name extraction uses [`google/flan-t5-small`](https://huggingface.co/google/flan-t5-small), a locally executed instruction-tuned language model. Its output is constrained: the extracted name must contain at least two words and must appear in the caller's original response after case and accent normalization. Ungrounded output is discarded rather than queried against customer data.

Customer lookup is accent-insensitive and case-insensitive. For example, `samuel andres diaz perez` matches the stored name `Samuel Andrés Díaz Pérez`; the official spelling from the database is used in the response.

Outcomes:

- One match creates a `DEMO_ONLY_NAME_MATCH` session.
- No match asks the caller to retry; two failures route to mock human handoff.
- Multiple matches do not authenticate and require human handoff.
- An empty or model-classified evasive answer produces an explanation, one retry and then handoff.
- A request for a human creates an immediate handoff.
- A low-confidence result asks the caller to clarify.
- A model loading or inference error fails closed to mock human handoff.

This is deliberately insecure demo identification. It must never protect real banking data or be described as production authentication.

## Run the automated tests

From the repository root:

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

The lightweight test environment does not install or download the ML model. Tests use `tests/fixtures/customers.csv` and inject a fake classification pipeline.

## Run the interactive demo with the full synthetic dataset

Install the local ML dependencies with the optional `ml` extra:

```bash
uv sync --extra ml
```

On Intel Macs, the project pins PyTorch 2.2.2 because newer PyTorch releases no longer publish macOS x86_64 wheels. It also uses NumPy 1.x and Transformers 4.x, which are compatible with that PyTorch build. Other supported platforms continue to use the current PyTorch release selected by `uv`.

Prepare the model once, before starting a customer interaction:

```bash
uv run --extra ml python -m dispute_agent.model_setup
```

The setup downloads the intent and name-extraction models from Hugging Face and validates the bundled language model. Customer interactions then load all models locally and do not make network requests. No API key or remote classification service is required.

```bash
uv run --extra ml python -m dispute_agent.cli \
  --customers /Users/silvs/Documents/projetos/visa-dispute-hackathon/data/raw/customers.csv \
  --language pt
```

Example successful name from the supplied synthetic dataset:

```text
Samuel Andrés Díaz Pérez
```

For a negative case, enter a name absent from the dataset. To test avoidance classification, answer `I prefer not to say`, `Why do you need it?`, or `Please give me a human`.

## Run with the small test fixture

```bash
uv run --extra ml python -m dispute_agent.cli --customers tests/fixtures/customers.csv
```

Use `--language pt`, `--language es` or `--language en` when the IVR already knows the caller's preference. The default `--language auto` uses the local language-identification model for free-form speech and accepts explicit menu choices directly. Add `--debug` only for development; customer-facing output hides internal IDs and assurance labels.

Use:

- `Ana Silva` for successful identification.
- `meu nome é José María Pérez López` for LLM-based name extraction against the small unit-test fixture.
- `Nobody Here` for no match.
- `Alex Santos` for the duplicate-name path.
- An empty answer or `Why do you need that?` for avoidance.

Automated tests inject a fake zero-shot pipeline, so they run without downloading the model or accessing the network. The interactive CLI uses the local model.

The supported commands use `python -m dispute_agent...` rather than relying on generated console scripts. The package lives at the project root, so Python can always import it from that directory—even on Homebrew installations that ignore editable-install `.pth` files marked as hidden by macOS.
