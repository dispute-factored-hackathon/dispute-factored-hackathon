# Dispute Factored Hackathon

Issuer-side Visa dispute resolution for the call-center channel.

Project documentation is maintained in the repository's [`docs`](../docs/README.md) directory. Open that directory as an Obsidian vault and start with `Home`.

## Synthetic GUI login contract

The GUI demo uses `GuiDemoLoginService` to populate a searchable e-mail dropdown. Search is partial and case-insensitive. Dropdown options expose only the normalized e-mail, safe location context, and a short-lived opaque selection token. Typing an e-mail is not enough to log in: the browser must submit a server-issued option token.

Selecting an option creates a short-lived server-side `AuthenticatedCustomerContext`. The customer ID is derived from that selection and is never accepted from chat text, a URL, or model output. Tokens are single-use, sessions expire, and logout revokes the session. This remains a deliberately insecure synthetic demo login and must not protect real banking data.

The GUI also reads country, preferred language, and locale from the selected synthetic customer record. It never invokes the language-detection model. Missing or invalid preferences use an explicit country default when supported, otherwise the product default (`en-US`); the source and fallback reason remain in the immutable session context for metrics and debugging. Voice country-code inference and GUI database preferences normalize to the same `ConversationLocaleContext`, while retaining different provenance.

`GuiDemoLoginService.language_metrics()` reports aggregate database-preference, country-fallback, product-fallback, and fallback-rate counters. It intentionally contains no customer values and reports `language_detection_model_calls: 0` as an architectural invariant of the GUI channel.

Run the local GUI login with the full synthetic customer table:

```bash
CUSTOMERS_CSV=../data/raw/customers.csv uv run python -m dispute_agent.gui_app
```

Then open `http://127.0.0.1:8000`. The current page ends after creating the demo session; the transaction page and dispute chat belong to the transaction-search workstream.

## Synthetic voice identity contract

`VoiceCallerIdentityService` first performs an exact normalized lookup of the supplied mobile phone. A unique match creates `DEMO_ONLY_PHONE_MATCH`. An unknown phone preserves only its calling-code hint and requires a `document_number`; a unique exact normalized document match creates `DEMO_ONLY_DOCUMENT_MATCH`. Neither mechanism is secure enough for real banking.

The service returns country and detected-accent data only from the matched synthetic customer record. It does not expose documents or phone numbers to the conversational model. The language branch consumes this deterministic result and owns the conversation state needed to keep or explicitly change language and accent.

The FastAPI voice contract is available at `/api/voice/calls`. A recognized phone starts in `authenticated` using the customer's country and compatible `detected_accent`. An unknown phone starts in `needs_language`, accepts the explicit preference at `/preferences`, and then collects the numeric synthetic document through `/dtmf`. Each OpenAI SIP `transport.dtmf.received` event maps to one request: `0`–`9` append, `*` clears, and `#` submits. Responses expose only the number of collected digits, never the document or buffer. The selected language and accent remain pinned after authentication. The same `/preferences` endpoint allows an explicit change at any later phase.

## Mock customer identification

The default agent is orchestrated with LangGraph. A single OpenAI Structured Output call receives the raw customer turn and returns a Pydantic-generated JSON Schema containing language, one closed intent class, confidence, prompt-abuse class, abuse confidence, grounded name extraction, and an optional scoped answer. No tokenization, label-vector mapping, regex intent preprocessing, or local zero-shot inference is required.

The schema recognizes `provides_name`, `asks_why`, `avoids_answer`, `requests_human`, `cancels`, `restarts`, `confirms`, `denies`, `selects_language`, `in_scope_question`, `out_of_scope`, and `other`. Low-confidence and `other` results never cause a consequential transition. Extracted names are accepted only when grounded in the customer's original utterance. Customer lookup, canonical names, customer IDs, authentication state, retry limits, confidence gates, and handoff decisions remain local and deterministic.

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
uv sync --dev
uv run python -m unittest discover -s tests -v
```

Tests use `tests/fixtures/customers.csv`, a fake structured model, and the complete synthetic database when available. They do not call the OpenAI API or consume credits.

Before opening a pull request, run the same quality checks used by GitHub Actions:

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
```

The pull-request workflow uses the committed lockfile, checks lint and formatting with Ruff, and then runs the complete test suite on Python 3.11.

For a machine-readable local evaluation summary, run:

```bash
uv run python -m dispute_agent.evaluation
```

This credential-free offline evaluation runs the same scenario suite and exits nonzero on any regression. Its JSON summary reports test count, failures, errors, skipped scenarios, and pass rate.

To evaluate the live structured-output model against the versioned synthetic benchmark:

```bash
uv run python -m dispute_agent.model_evaluation
```

To evaluate country-code inference, regional locale selection, ambiguity handling, language order,
and opening latency against `evals/openings.jsonl`:

```bash
uv run python -m dispute_agent.language_evaluation
```

This produces JSON metrics for intent accuracy, language accuracy, accent-insensitive name extraction, answer presence, prompt-abuse accuracy/precision/recall/F1, complete-example accuracy, average latency, p95 latency, API calls, and individual failures. The benchmark lives in `evals/turns.jsonl`; it contains only synthetic multilingual examples.

To upload the same benchmark and row-level scores as a LangSmith experiment:

```bash
LANGSMITH_TRACING=true uv run python -m dispute_agent.model_evaluation --langsmith
```

The command creates `visa-dispute-authentication-turns-v1` when it does not exist and records five deterministic evaluators: intent, language, abuse, name extraction, and expected answer presence. Use `--dataset NAME` to target a separately versioned dataset rather than silently changing an existing benchmark.

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

Tracing is disabled by default. To inspect graph and model runs in LangSmith, set `LANGSMITH_TRACING=true` and provide a project-scoped `LANGSMITH_API_KEY`. Explicit spans identify call start, country-context inference, each customer turn, schema classification, LangGraph nodes, and the underlying model request. Public turns include a random opaque `thread_id` and only non-sensitive metadata (locale, phase, channel, and the `synthetic_data` flag) for filtering and multi-turn grouping. The trace payload itself contains the customer utterance and model output, so enable tracing only with synthetic data in this prototype. Never put real names, account information, secrets, or production banking data in these traces.

Use the local evaluation command for pull-request and offline regression checks. LangSmith datasets and online evaluators can be added later when the team has an approved workspace, privacy policy, sampling policy, and production-like labeled examples.

## Direct answers and abuse controls

The graph can directly answer short questions about the agent's identity, role, capabilities, limitations, disputes, fraud, refunds, chargebacks, evidence, identity collection, and next steps. The same schema-constrained call classifies and answers the turn from a small approved knowledge block. It has no database or tool access. If the same utterance contains a grounded full name, name extraction takes priority and the identification flow continues.

Controls are layered rather than delegated entirely to the model:

- a reusable ingress decorator applies prompt-abuse screening to every non-empty, size-valid customer message before graph execution;
- customer text is explicitly treated as untrusted data;
- the structured schema classifies prompt manipulation, hidden-instruction extraction, credential extraction, and unrelated-data access attempts in the same bounded LLM call;
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
uv sync --dev
uv run python -m dispute_agent.cli \
  --customers /Users/silvs/Documents/projetos/visa-dispute-hackathon/data/raw/customers.csv \
  --country-code +55
```

The telephone country code is the only caller-context input. The multilingual LLM infers a likely country, primary language, and regional locale, then generates the welcome and language question. It does not treat this inference as verified location. Shared codes such as `+1`, and unknown codes, are described as ambiguous instead of being assigned to a country.

The selected language is also regionalized for the rest of the interaction: Brazil uses Brazilian Portuguese (`pt-BR`), Colombia uses Colombian Spanish (`es-CO`), Mexico uses Mexican Spanish (`es-MX`), Argentina uses Argentine Spanish with voseo (`es-AR`), and English uses American English (`en-US`). When the caller chooses a language different from the country's main language, the agent uses American English, Brazilian Portuguese, or neutral Latin American Spanish (`es-419`) as the corresponding fallback.

```bash
uv run python -m dispute_agent.cli \
  --customers ../data/raw/customers.csv \
  --country-code +55
```

Example successful name from the supplied synthetic dataset:

```text
Samuel Andrés Díaz Pérez
```

For a negative case, enter a name absent from the dataset. To test avoidance classification, answer `I prefer not to say`, `Why do you need it?`, or `Please give me a human`.

## Run with the small test fixture

```bash
uv run python -m dispute_agent.cli --customers tests/fixtures/customers.csv --country-code +55
```

There is one multilingual agent, not separate agents per language. It asks the caller to choose a language, can infer the language of a substantive free-form answer, and then keeps the selected regional locale for the session. Add `--debug` only for development; customer-facing output hides internal IDs and assurance labels.

Use:

- `Ana Silva` for successful identification.
- `meu nome é José María Pérez López` for LLM-based name extraction against the small unit-test fixture.
- `Nobody Here` for no match.
- `Alex Santos` for the duplicate-name path.
- An empty answer or `Why do you need that?` for avoidance.

Automated tests inject a fake structured model, so they run without accessing the network. The interactive CLI uses the model configured by `OPENAI_AGENT_MODEL`.

The supported commands use `python -m dispute_agent...` rather than relying on generated console scripts. The package lives at the project root, so Python can always import it from that directory—even on Homebrew installations that ignore editable-install `.pth` files marked as hidden by macOS.
