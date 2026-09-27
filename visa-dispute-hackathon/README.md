# Dispute Factored Hackathon

Issuer-side Visa dispute resolution for the call-center channel.

Project documentation is maintained in the repository's [`docs`](../docs/README.md) directory. Open that directory as an Obsidian vault and start with `Home`.

## Mock customer identification

The default agent is orchestrated with LangGraph. The LLM extracts a caller-stated name and may answer an allowed dispute question directly. Whenever the conversation must choose a state-changing branch, the graph uses a local multilingual zero-shot classifier. The graph advances only when the top class is not `other`, meets the configured confidence threshold, and—during name confirmation—also meets the minimum score margin.

The zero-shot model recognizes `provides_name`, `avoids_answer`, `asks_why`, `requests_human`, and `other`; confirmation uses `confirms`, `denies`, and `other`. Low-confidence and `other` results never change conversation state. OpenAI structured output is validated with Pydantic, and extracted names are accepted only when grounded in the customer's original utterance. The complete customer database, customer IDs, match results, authentication state, retry limits, and handoff decisions remain local and deterministic.

After finding one customer, the agent repeats the canonical database spelling and asks the caller to confirm it. Authentication completes only after confirmation. A correction such as `não, meu nome é José María Pérez López` is extracted, looked up locally, and presented for confirmation in the same turn.

Customer lookup is accent-insensitive and case-insensitive. For example, `samuel andres diaz perez` matches the stored name `Samuel Andrés Díaz Pérez`; the official spelling from the database is used in the response.

Outcomes:

- One match triggers an explicit name-confirmation question. Confirmation creates a `DEMO_ONLY_NAME_MATCH_CONFIRMED` session.
- A denial asks for the correct name. If the correction is included in the denial, the agent extracts and looks it up in the same turn.
- No match asks the caller to retry; two failures route to mock human handoff.
- Multiple matches do not authenticate and require human handoff.
- An empty or model-classified evasive answer produces an explanation, one retry and then handoff.
- A request for a human creates an immediate handoff.
- Human, cancel, and restart requests are available in every phase, including name confirmation.
- Handoff notes preserve the current phase, pending name, confirmation state, last customer request, and previous agent question so the customer does not need to repeat the interaction.
- A low-confidence result asks the caller to clarify.
- A first model loading or inference error offers one deterministic recovery path; a repeated failure closes safely through mock human handoff.

Control commands use word boundaries and command-shaped phrases. Ordinary questions containing words such as `cancelamento`, `agente`, or `parece` are not treated as cancel or handoff instructions.

This is deliberately insecure demo identification. It must never protect real banking data or be described as production authentication.

## Run the automated tests

From the repository root:

```bash
uv sync --extra ml
uv run --extra ml dispute-auth-setup
uv run --extra ml python -m unittest discover -s tests -v
```

Tests use `tests/fixtures/customers.csv`, a fake structured model, and the complete synthetic database when available. They do not call the OpenAI API or consume credits.

For a machine-readable local evaluation summary, run:

```bash
uv run --extra ml dispute-agent-eval
```

This credential-free offline evaluation runs the same scenario suite and exits nonzero on any regression. Its JSON summary reports test count, failures, errors, skipped scenarios, and pass rate.

## Configure the OpenAI API

Create `.env` from the safe template and provide a project-scoped key. The real `.env` is ignored by Git.

```bash
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=your-project-key
OPENAI_AGENT_MODEL=gpt-4.1-mini
MAX_LLM_CALLS_PER_SESSION=20
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=visa-dispute-hackathon
LANGSMITH_API_KEY=
```

Customer utterances are sent to OpenAI for structured interpretation. Do not use real customer or banking data in this hackathon prototype.

## Optional LangSmith tracing

Tracing is disabled by default. To inspect graph and model runs in LangSmith, set `LANGSMITH_TRACING=true` and provide a project-scoped `LANGSMITH_API_KEY`. Public turns include a random opaque `thread_id` and only non-sensitive metadata (locale, phase, channel, and the `synthetic_data` flag) for filtering and multi-turn grouping. The trace payload itself contains the customer utterance and model output, so enable tracing only with synthetic data in this prototype. Never put real names, account information, secrets, or production banking data in these traces.

Use the local evaluation command for pull-request and offline regression checks. LangSmith datasets and online evaluators can be added later when the team has an approved workspace, privacy policy, sampling policy, and production-like labeled examples.

## Direct answers and abuse controls

The graph can directly answer short questions about the agent's identity, role, capabilities, limitations, disputes, fraud, refunds, chargebacks, evidence, identity collection, and next steps. These conversational questions do not pass through workflow intent classification. This route has no database or tool access and may answer only from a small approved knowledge block. If the same utterance contains a grounded full name, name extraction takes priority and the identification flow continues.

Controls are layered rather than delegated entirely to the model:

- a reusable ingress decorator applies prompt-abuse screening to every non-empty, size-valid customer message before graph execution;
- customer text is explicitly treated as untrusted data;
- a local zero-shot safety model detects prompt manipulation, hidden-instruction extraction, credential extraction, and unrelated-data access attempts before an API call;
- abuse blocking requires both a high-confidence abuse class and a minimum probability margin, reducing false positives on legitimate banking questions;
- inputs are limited to 500 characters and sessions default to 20 uncached LLM calls;
- repeated turns use a phase-and-locale-aware cache;
- unrelated requests receive a fixed scope response;
- generated answers are length-limited and rejected if they contain internal-instruction, credential, code-block, or URL markers;
- the model has no customer-database or tool access; and
- API errors or exhausted limits fail closed to the existing human-handoff path.

LangChain provides `@before_agent` and `@before_model` middleware decorators for agents created with its high-level `create_agent` API. This prototype uses a custom LangGraph `StateGraph`. The public `handle_answer` decorator identifies the shared ingress, while the explicit `screen_abuse` graph node performs the authoritative check exactly once and also protects direct compiled-graph invocation. No caller-provided flag can skip this node. This keeps the safety boundary at every customer-message ingress rather than relying on individual business branches.

The current CLI creates one agent object for one caller. Cross-turn counters, the pending customer, model-call budget, and caches live in that object rather than checkpointed LangGraph state. Do not share one instance between callers or present this build as restart-resumable. Before deploying a web, voice, or concurrent service, move authoritative session data into serializable graph state or a dedicated session store, add an appropriate checkpointer, and use stable opaque thread identifiers.

## Run the interactive demo with the full synthetic dataset

```bash
uv sync --extra ml
uv run --extra ml dispute-auth-demo \
  --customers /Users/silvs/Documents/projetos/visa-dispute-hackathon/data/raw/customers.csv \
  --country-code +55 \
  --language auto
```

When `--language auto` is used, `--country-code` localizes the opening without forcing the customer's choice. Spanish-speaking country codes open in Spanish and offer Spanish, English, then Portuguese. Portuguese-speaking codes open in Portuguese and offer Portuguese, English, then Spanish. Other or unknown codes open in English and offer English, Spanish, then Portuguese.

The selected language is also regionalized for the rest of the interaction: Brazil uses Brazilian Portuguese (`pt-BR`), Colombia uses Colombian Spanish (`es-CO`), Mexico uses Mexican Spanish (`es-MX`), Argentina uses Argentine Spanish with voseo (`es-AR`), and English uses American English (`en-US`). When the caller chooses a language different from the country's main language, the agent uses American English, Brazilian Portuguese, or neutral Latin American Spanish (`es-419`) as the corresponding fallback.

```bash
uv run --extra ml dispute-auth-demo \
  --customers ../data/raw/customers.csv \
  --country-code +55 \
  --language auto
```

Example successful name from the supplied synthetic dataset:

```text
Samuel Andrés Díaz Pérez
```

For a negative case, enter a name absent from the dataset. To test avoidance classification, answer `I prefer not to say`, `Why do you need it?`, or `Please give me a human`.

## Run with the small test fixture

```bash
uv run --extra ml dispute-auth-demo --customers tests/fixtures/customers.csv
```

Use `--language pt`, `--language es` or `--language en` when the IVR already knows the caller's preference. The default `--language auto` accepts explicit menu choices and uses the structured LLM when language must be inferred from free-form text. Add `--debug` only for development; customer-facing output hides internal IDs and assurance labels.

Use:

- `Ana Silva` for successful identification.
- `meu nome é José María Pérez López` for LLM-based name extraction against the small unit-test fixture.
- `Nobody Here` for no match.
- `Alex Santos` for the duplicate-name path.
- An empty answer or `Why do you need that?` for avoidance.

Automated tests inject a fake structured model, so they run without accessing the network. The interactive CLI uses the model configured by `OPENAI_AGENT_MODEL`.

The supported commands use `python -m dispute_agent...` rather than relying on generated console scripts. The package lives at the project root, so Python can always import it from that directory—even on Homebrew installations that ignore editable-install `.pth` files marked as hidden by macOS.
