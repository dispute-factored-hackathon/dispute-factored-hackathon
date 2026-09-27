# Dispute Factored Hackathon

Issuer-side Visa dispute resolution for the call-center channel.

Project documentation is maintained in the [GitHub Wiki](https://github.com/dispute-factored-hackathon/dispute-factored-hackathon/wiki).

## Mock customer identification

The first implemented layer asks `What is your full name?`. Jev categorizes the response as `provides_name`, `avoids_answer`, `asks_why`, `requests_human` or `other`. A high-confidence name response is normalized and looked up in the synthetic `customers.csv` file.

Outcomes:

- One match creates a `DEMO_ONLY_NAME_MATCH` session.
- No match asks the caller to retry; two failures route to mock human handoff.
- Multiple matches do not authenticate and require human handoff.
- An empty or Jev-classified evasive answer produces an explanation, one retry and then handoff.
- A request for a human creates an immediate handoff.
- A low-confidence Jev result asks the caller to clarify.
- A Jev error fails closed to mock human handoff.

This is deliberately insecure demo identification. It must never protect real banking data or be described as production authentication.

## Run the automated tests

From the repository root:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The tests use `tests/fixtures/customers.csv`; the full dataset is not required.

## Run the interactive demo with the full synthetic dataset

Create a TypeSafe API key in the [TypeSafe console](https://console.typesafe.ai/) and export it in your terminal:

```bash
export TYPESAFE_API_KEY="your-key"
```

The key stays server-side and must not be committed. The integration calls the official `https://api.typesafe.ai/v1/systemone` endpoint with model `jev-latest`.

```bash
PYTHONPATH=src python3 -m dispute_agent.cli \
  --customers /Users/silvs/Documents/projetos/visa-dispute-hackathon/data/raw/customers.csv
```

Example successful name from the supplied synthetic dataset:

```text
Samuel Andrés Díaz Pérez
```

For a negative case, enter a name absent from the dataset. To test Jev avoidance classification, answer `I prefer not to say`, `Why do you need it?`, or `Please give me a human`.

## Run with the small test fixture

```bash
PYTHONPATH=src python3 -m dispute_agent.cli --customers tests/fixtures/customers.csv
```

Use:

- `Ana Silva` for successful identification.
- `Nobody Here` for no match.
- `Alex Santos` for the duplicate-name path.
- An empty answer or `Why do you need that?` for avoidance.

Automated tests inject a fake typed Jev classifier, so they run without an API key or network access. The interactive CLI uses the live Jev API.
