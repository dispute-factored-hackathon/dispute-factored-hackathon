# Dispute Factored Hackathon

Issuer-side Visa dispute resolution for the call-center channel.

Project documentation is maintained in the repository's [`docs`](../docs/README.md) directory. Open that directory as an Obsidian vault and start with `Home`.

## Synthetic GUI login contract

The GUI demo uses `GuiDemoLoginService` to populate a searchable e-mail dropdown. Search is partial and case-insensitive. Dropdown options expose only the normalized e-mail, safe location context, and a short-lived opaque selection token. Typing an e-mail is not enough to log in: the browser must submit a server-issued option token.

Selecting an option creates a short-lived server-side `AuthenticatedCustomerContext`. The customer ID is derived from that selection and is never accepted from chat text, a URL, or model output. Tokens are single-use, sessions expire, and logout revokes the session. This remains a deliberately insecure synthetic demo login and must not protect real banking data.

Run the local GUI login with the full synthetic customer table:

```bash
CUSTOMERS_CSV=../data/raw/customers.csv uv run python -m dispute_agent.gui_app
```

Then open `http://127.0.0.1:8000`. The current page ends after creating the demo session; the transaction page and dispute chat belong to the transaction-search workstream.

## Synthetic voice identity contract

`VoiceCallerIdentityService` first performs an exact normalized lookup of the supplied mobile phone. A unique match creates `DEMO_ONLY_PHONE_MATCH`. An unknown phone preserves only its calling-code hint and requires a numeric `document_number`; a unique exact normalized document match creates `DEMO_ONLY_DOCUMENT_MATCH`. The telephone integration must collect this value from DTMF keypad events rather than speech or model extraction. Alphanumeric documents require human fallback because a numeric telephone keypad cannot represent them unambiguously. Neither mechanism is secure enough for real banking.

The service returns country and detected-accent data only from the matched synthetic customer record. It does not expose documents or phone numbers to the conversational model. The language branch consumes this deterministic result and owns the conversation state needed to keep or explicitly change language and accent.

## Test a real phone call through SIP and OpenAI Realtime

The SIP adapter in `dispute_agent.sip_realtime` implements the inbound Realtime flow: it verifies the OpenAI webhook signature, deduplicates retries, accepts the call, and opens a private sideband WebSocket. The SIP provider and OpenAI carry the audio; this backend owns authentication state, language changes, DTMF document entry, and tool results.

For this synthetic demo, `DEMO_LOG_FULL_TRANSCRIPTS=true` enables OpenAI input-audio transcription and stores every completed customer and agent utterance in CloudWatch as a `voice.transcript.completed` JSON event. The `transcript` value is written exactly as received, without redaction or truncation, and `speaker` identifies `customer` or `agent`. This mode must only be used with fake data: disable it before adapting the service to real customers, and never speak real credentials, document numbers, card numbers, or other secrets during a demo call. Keypad document digits remain outside the verbal transcript and are not logged.

The caller number is evaluated before the model speaks. A unique exact normalized match in `customers.mobile_phone` authenticates the synthetic customer and loads language, country, and accent from that customer record. If the complete number is not found or is ambiguous, it does not authenticate: only the international calling code is used as a regional language/accent hint, the caller confirms or changes the language, and authentication continues with keypad-only document entry. An explicit language change updates the active Realtime session instructions for the rest of the call.

This remains a synthetic demonstration. A SIP `From` header can be spoofed and is explicitly treated as untrusted metadata by OpenAI. Even when it uniquely matches the synthetic table, `DEMO_ONLY_PHONE_MATCH` is not production-grade authentication.

### Hybrid Jev and Realtime decision boundary

The call worker sends each completed synthetic caller transcript to TypeSafe Jev before asking the Realtime model to act. Jev handles only bounded decisions with typed probabilities: prompt abuse, an explicit human request, initial language choice, authentication method, transaction confirmation, fraud-versus-duplicate classification, card environment, and the optional satisfaction rating. High-confidence decisions call the existing server-owned tools directly. Low-confidence, unavailable, open-ended, or composite cases fall back to Realtime without failing the call.

OpenAI Realtime remains responsible for speech recognition, speech generation, contextual questions, and extracting variable transaction-search fields such as merchant, approximate amount, date, and location. A denial that also contains corrected transaction details deliberately falls back so Realtime can extract those details; Jev still provides the global abuse and human-request guard. The backend continues to own identity, transaction access, Visa mapping, card blocking, complaint filing, and human transfer.

`JEV_API_KEY` is server-only. It must stay in `.env` locally and in the existing combined Secrets Manager JSON in AWS; it must never be sent to a browser, included in a model prompt, or written to logs. Jev telemetry contains only model, action, confidence, latency, and token counts. Because the external decision request contains the completed caller transcript, this integration is authorized only for the synthetic demonstration data used by this repository.

### Voice transaction search

After authentication, Izzy asks whether the caller is having a problem with a transaction. The caller can describe a merchant or descriptor, approximate amount, currency, date or date range, country, city, channel, or transaction type. The Realtime model passes only schema-constrained criteria to the backend; it never sends executable SQL.

The voice channel shares the web app's PostgreSQL. `RepositoryTransactionSearch` reads the authenticated caller's card transactions through the `TransactionRepository` contract. Those transactions come from `dispute-db-seed-lakehouse` (synthetic lakehouse data) plus purchases made in the web shop. Nothing is seeded in code. `SQLiteTransactionSearchRepository` remains as an isolated adapter over transactions the caller supplies; the tests use it with ten synthetic fruit purchases.

The backend uses a small, structured RAG pipeline for every search turn:

1. **Retrieve:** the authenticated customer's most recent untried transactions are read through the repository contract (parameterized SQL in PostgreSQL), at most 500.
2. **Rerank:** an explainable ranker scores the retrieved candidates against only the details supplied by the caller. Merchant similarity has the greatest weight, followed by amount proximity, date, location, currency, channel, and transaction type.
3. **Top-1:** only the highest-ranked relevant transaction is given to Izzy for presentation and explicit confirmation.
4. **Refine:** whenever the caller adds or corrects a detail, the backend merges the new criteria and repeats retrieval, reranking, and Top-1 selection from the beginning.

The retrieval boundary guarantees that:

- the authenticated `customer_id` is always injected by trusted server state;
- approximate amounts are ranked by their distance using the greater of five currency units or 10% as the scale;
- values are bound parameters and cannot alter the statement;
- only the known `transactions` table and supported filters are used;
- no more than ten ranked candidates are returned;
- denied candidates are excluded from later proposals.

Izzy speaks one ranked candidate at a time with merchant, date, amount/currency, city, and country. Only an explicit confirmation selects it. After each denial, Izzy asks for exactly one useful detail that has not already been requested before running retrieval and reranking again. If the caller cannot provide that detail, Izzy moves to a different question instead of repeating the same search. Refining the current candidate does not consume an additional guess; only an explicit denial does. After three denied candidates, Izzy preserves the search context and starts the same human-handoff path available through an explicit caller request. The backend, not the model, resolves the fixed destination and asks OpenAI to relay a SIP REFER only after Izzy finishes the transfer notice.

Every search response states the active filters in the caller's selected language. The caller can correct a filter value, remove one named filter, or clear all filters and begin again. A correction reruns retrieval and reranking without consuming another candidate guess. Three rejected candidates or three searches with no matching transaction lead to the same simulated-human-handoff boundary.

When a caller rejects a candidate and provides a new detail in the same sentence, the backend records both atomically: the rejected transaction is excluded and the new detail immediately reruns retrieval. A completed speech transcript must contain an explicit yes before a transaction can be confirmed; unclear transcription asks the caller to repeat instead of guessing. Amounts and dates inferred by the model are dropped when the spoken turn contains no matching numeric evidence, preventing unsupported filters from steering the ranker.

### Mock Visa classification after transaction selection

After the caller confirms a transaction, Izzy asks whether the customer did not make or authorize it, or recognizes the purchase but was charged more than once for the same purchase. Jev returns one typed allegation with probabilities: `UNAUTHORIZED_CARD`, `DUPLICATE_PROCESSING`, or `INSUFFICIENT_INFO`. The channel-agnostic `DisputeClassificationService` then validates the required evidence and owns the mapping:

- unauthorized plus a card-present channel → Visa 10.3, Other Fraud — Card-Present Environment;
- unauthorized plus a card-absent channel → Visa 10.4, Other Fraud — Card-Absent Environment;
- one recognized purchase charged more than once → Visa 12.6.1, Duplicate Processing.

Ambiguous, missing, or conflicting evidence produces no code and one neutral clarification question. The result is stored in the synthetic call state with the allegation, candidate Visa code, workflow, supporting evidence, missing evidence, transaction reference, and channel. Structured logs expose class, code, clarification rate, and latency without customer identity or transaction IDs.

This is an intake recommendation, not a final fraud finding or Visa eligibility decision. After a validated unauthorized-card classification, the call demo automatically blocks the synthetic card that the confirmed transaction was charged to; duplicate and inconclusive reports never trigger or suggest a block. The state change uses the backend product service, validates customer ownership, is idempotent, and is visible in the web app because both channels share the same PostgreSQL. The demo does not submit a chargeback, issue a refund, query VROL, retrieve issuer/network evidence, or order a replacement card. The shared classifier is independent of SIP so a later GUI chat can call the same contract; the current `/agent` GUI remains a placeholder.

### Complaint persistence after classification

After a supported Visa condition is validated, the server—not the language model—creates a
trackable complaint through the shared `ComplaintRepository` contract, stored in the same
PostgreSQL as the web app (`DATABASE_URL`, used by both the local SIP server and the Lambda worker).

The complaint follows the synthetic `complaints` table: it belongs to the authenticated customer,
links the selected card product, records the Realtime call as its origin interaction, uses `Call
Center` as the reception channel, copies the claimed transaction amount and currency, assigns
`IZZY`, and starts in `In Review`. Its Visa-derived subcategory is one of Visa 10.3, 10.4, or
12.6.1. A deterministic opaque complaint ID makes a repeated write for the same call idempotent.
Only after the repository returns the stored complaint does Izzy speak its identifier, Visa code,
and status. A storage failure is disclosed and must never be described as a successfully filed
complaint.

This creates a synthetic bank complaint, not a Visa chargeback or a final liability decision.
PostgreSQL and memory behavior are covered by the same repository contract tests.

Run the SQLite, state-machine, and SIP-sideband coverage with:

```bash
uv run pytest tests/test_transaction_search.py tests/test_dispute_classification.py tests/test_voice_call.py tests/test_sip_realtime.py -q
```

### 1. Configure and start the backend

Copy `.env.example` to `.env`, then set `OPENAI_API_KEY`, `OPENAI_WEBHOOK_SECRET`, and the customer table. For a safe first call, use the fixture:

```dotenv
CUSTOMERS_CSV=tests/fixtures/customers.csv
OPENAI_REALTIME_MODEL=gpt-realtime-2.1
OPENAI_REALTIME_VOICE=cedar
HUMAN_HANDOFF_NUMBER=+5511981020050
PORT=8001
```

Install and start the service:

```bash
uv sync --group dev
uv run dispute-sip-server
```

Check `http://127.0.0.1:8001/health`. A local HTTPS tunnel remains useful for short development sessions. The AWS deployment below replaces the tunnel with a stable HTTPS Lambda Function URL.

### Cost-conscious AWS deployment

The hackathon deployment intentionally avoids always-on or redundant services. It does **not** create App Runner, ECS/Fargate, EC2, an Application Load Balancer, API Gateway, a NAT Gateway, Route 53, ACM, DynamoDB, or a VPC.

The components are:

- **Lambda Function URL:** free HTTPS endpoint layer; standard Lambda invocation and duration charges still apply. It receives the signed OpenAI webhook.
- **Lambda ingress invocation:** verifies the signature and accepts the SIP call immediately.
- **Lambda asynchronous worker invocation:** opens the private Realtime sideband WebSocket for the duration of the call. It stops at 14 minutes, before Lambda's 15-minute limit.
- **ECR:** stores the immutable Docker image and retains only the three newest images.
- **One Secrets Manager secret:** stores `OPENAI_API_KEY`, `OPENAI_WEBHOOK_SECRET`, and `JEV_API_KEY`. It is fetched once per Lambda execution environment rather than on every message or keypad event.
- **CloudWatch Logs:** keeps JSON logs for three days. The application never logs document digits.
- **Concurrency:** uses the account's unreserved Lambda capacity. The demo account currently has a total concurrency quota of 10, so the stack does not reserve concurrency; AWS requires all 10 executions to remain unreserved at that quota. Use account quotas and OpenAI-side limits as the cost and abuse boundary until the Lambda quota is increased.

The call media does not pass through AWS:

```text
Caller → SIP provider → OpenAI Realtime
                           │
                           ├─ signed webhook → Lambda Function URL
                           └─ private sideband ↔ Lambda call worker
```

This arrangement has no continuously running compute. Lambda is billed only while the short webhook and active call worker execute. The Function URL has no separate endpoint charge. One Secrets Manager secret currently has a small recurring charge, and ECR and CloudWatch are usage-based. OpenAI Realtime and the SIP provider are billed separately.

Prerequisites are an AWS account, an AWS CLI profile with deployment permissions, and Docker Buildx. From `visa-dispute-hackathon/`, create the persistent ECR repository and secret:

```bash
AWS_REGION=sa-east-1 ./infra/aws/deploy.sh bootstrap
```

Open **AWS Secrets Manager → dispute-factored/openai-realtime** and replace `OPENAI_API_KEY` and `JEV_API_KEY`; the webhook value can remain `replace-me` until the endpoint exists:

```json
{
  "OPENAI_API_KEY": "your-project-key",
  "OPENAI_WEBHOOK_SECRET": "replace-me",
  "JEV_API_KEY": "your-typesafe-key"
}
```

Do not commit this value or pass it as a CloudFormation parameter. Then build the Lambda container for Linux, push it to ECR, and deploy the function:

```bash
AWS_REGION=sa-east-1 ./infra/aws/deploy.sh application
```

The command prints an `https://...lambda-url.../webhooks/openai` address. Use that exact value to create the OpenAI project webhook, copy its new signing secret, and replace `OPENAI_WEBHOOK_SECRET` in the same AWS secret **before placing the first call**. No Lambda environment has started yet, so the first call reads the correct value. After a later secret rotation, deploy a new image tag to replace any warm environments.

The infrastructure definitions are split because ECR must exist before Docker can push the image:

- `infra/aws/bootstrap.yaml`: ECR and the retained secret.
- `infra/aws/application.yaml`: IAM with least-privilege policies, Lambda, Function URL, bounded asynchronous invocation, and log retention.
- `Dockerfile.aws`: reproducible Python 3.12 Lambda image using the locked `uv` dependencies. BuildKit adds only `data/raw/customers.csv` from the supplied 150,000-row synthetic dataset; it does not upload the other raw tables to Docker.
- `infra/aws/deploy.sh`: repeatable bootstrap/build/deploy commands.

### Automated deployments from GitHub

`.github/workflows/deploy-aws.yml` validates and deploys the same application flow when:

- a pull request is actually merged into `main` (closing without merging is ignored);
- a GitHub release is published; or
- a maintainer starts the workflow manually.

The workflow uses GitHub OIDC to obtain short-lived AWS credentials. It does not store an AWS access key. The one-time role is defined in `infra/aws/github-actions-role.yaml`; deploy that stack and save its `RoleArn` as the repository Actions secret `AWS_DEPLOY_ROLE_ARN`. Its trust policy accepts only this repository's merged-PR event, `main`, and release tags. Manual deployments must be started from `main`. The trust policy uses GitHub's immutable organization and repository IDs in addition to their names because those IDs are present in the repository's OIDC `sub` claim; if the repository is moved or recreated, update both ID parameters before deploying the role stack.

The complete synthetic customer table is intentionally not committed. On GitHub-hosted runners, the deploy script extracts `customers.csv` from the newest immutable image already present in the project's ECR repository, then embeds it in the new image. Consequently, the first deployment must still be performed locally with `CUSTOMERS_BUILD_CONTEXT` pointing to a directory containing `customers.csv`. Subsequent automated deployments need no additional data service or paid storage.

Each deployment uses the full Git commit SHA as its immutable image tag, runs Ruff and the complete unit-test suite, validates both CloudFormation templates, updates the application stack, and verifies that an unsigned webhook request is rejected with `invalid_webhook_signature`.

To remove active compute and the public endpoint after the demonstration while deliberately retaining the image repository and secret:

```bash
aws cloudformation delete-stack --stack-name dispute-factored-demo --region sa-east-1
```

The retained bootstrap resources continue to incur their small storage charges until explicitly emptied/deleted. CloudFormation will not silently destroy the secret.

### Configure the OpenAI project

In the OpenAI platform, open **Settings → Project → Webhooks**. Create a webhook pointing to:

```text
https://YOUR-LAMBDA-FUNCTION-URL/webhooks/openai
```

Subscribe to `realtime.call.incoming` and copy its signing secret into the configured secret. Restart the local backend when using `.env`; for AWS, update Secrets Manager before the first call. Use the project ID shown under **Project → General** in the next step; it begins with `proj_`.

### Connect a phone number

In a SIP trunk provider such as Twilio, create an Elastic SIP Trunk, enable secure trunking, associate a telephone number, and set its Origination SIP URI to:

```text
sip:YOUR_OPENAI_PROJECT_ID@sip.api.openai.com;transport=tls
```

The provider must send TLS signaling and SRTP media. Then call the number associated with the trunk. A trial provider account may require the calling number to be verified first.

### Transfer to human support

Izzy exposes a global `request_human` intent during every active language, authentication,
transaction-search, confirmation, classification, and satisfaction phase. An explicit request for
a person takes priority over the phase-specific tool. Frustration or a generic request for help does
not trigger a transfer. Exhausted document-authentication or transaction-search attempts enter the
same path automatically.

The transfer destination comes only from the server-owned `HUMAN_HANDOFF_NUMBER` setting and is
never accepted from caller speech or model arguments. The demo rejects a transfer when the fixed
destination is the same as the calling phone, permits only the backend to execute the OpenAI
Realtime `refer` operation, stores the interaction and transcript before transfer, and logs the
result without the destination number. The current configuration targets `+5511981020050`; place
the test call from a different telephone.

In the Twilio Elastic SIP Trunk console, enable **Call Transfer (SIP REFER)** and **Call transfers
to the PSTN**. A successful REFER is a blind transfer: the human receives the live call, while the
structured context remains in the demo repositories and logs. There is no contact-center desktop or
agent whisper in this prototype. If the destination is missing, matches the caller, or the provider
rejects the REFER, Izzy explains the limitation instead of claiming a successful transfer.

With the local `tests/fixtures/customers.csv`, a real caller number normally will not match the fake phone values. The AWS image instead contains the complete supplied synthetic `customers.csv`; it still normally will not contain the caller's real number. The expected fallback test is therefore:

1. the agent infers a regional opening from the real calling code and asks for English, Spanish, or Portuguese;
2. say the preferred language;
3. enter `123456789#` on the keypad to match the fake Colombian customer;
4. use `*` to clear mistyped digits;
5. try an unknown number three times to verify simulated human handoff.

The document digits are accumulated and checked only in backend memory. They are not placed in model prompts, tool outputs, responses, or application logs. Automated webhook, signature-failure, duplicate-delivery, locale, DTMF, success, and handoff scenarios run without placing a real call:

```bash
uv run python -m unittest tests.test_sip_realtime tests.test_voice_call -v
```

## Run the web app (PostgreSQL + lakehouse seed)

The web app stores customers, cards (bank products), transactions, complaints and sessions only in a local PostgreSQL started with Docker. It does not start without that database, and it no longer creates customers or history in code. All customer data is copied from the synthetic hackathon lakehouse (`lakehouse.silver` on MotherDuck, read-only). Copy `.env.example` to `.env` and fill in the passwords and `MOTHERDUCK_TOKEN`. Then run, from this directory:

```powershell
docker compose up -d db
uv sync
uv run dispute-db-migrate
uv run dispute-db-seed-lakehouse --dry-run      # read and validate only
uv run dispute-db-seed-lakehouse                # 100 active customers, about 2,000 transactions
uv run uvicorn webapp.backend.main:app --port 8000
```

The seed picks active customers with an active credit card and at least one transaction, in a stable order. Re-running it is safe because existing rows are kept. It refuses non-local databases unless `--allow-remote` is passed, and it warns when fewer than 1,000 transactions are available. Use `--customers N` for a different sample. Card numbers are masked to the last four digits before they leave the lakehouse query.

New sign-ups get one demo credit card and no history. Their transactions come from purchases in `/shop`, and those purchases are what they can later dispute.

Tests: `uv run pytest -q`. Web and voice tests use the in-memory test doubles and synthetic fixtures in `tests/fakes.py`. The PostgreSQL integration tests run only when `TEST_POSTGRES_URL` points at a disposable server (`postgresql://postgres:<password>@127.0.0.1:<port>/postgres`). Otherwise they are skipped.

The voice channel (`dispute-sip-server` and the Lambda worker) uses the same database through `DATABASE_URL`, so customers, cards, transactions and complaints are shared between phone and web. A deployed worker needs a PostgreSQL it can reach; it does not create demo customers.

Limitations: the data is synthetic, and the parody shop catalog is static copy. Purchases and complaints written by the app or by calls exist only in PostgreSQL; they are not synchronized back to the lakehouse yet.

## Izzy web chat (`/agent`)

Signed-in customers can chat with Izzy from the Izzy tab, or from **Report** on a transaction (`/agent?transaction_id=…`). The chat is mobile-first and streams Izzy's replies. The page also shows Izzy's phone line (`IZZY_PHONE_NUMBER`, served by `GET /api/izzy/contact`) as the alternative channel.

How it works:

- **Customer context:** the customer comes from the web session cookie, so Izzy greets them by name and never asks for the Factored ID, phone, or document again. The session id is bound to that customer; any other customer gets `404`.
- **Same workflow as calls:** `dispute_agent/web_chat` contains the chat's own LangGraph graph (`guard_input → interpret → screen_abuse → global_controls → workflow → compose_reply`). It runs on `WebChatDisputeService`, a subclass of `VoiceCallService`, so it reuses the call stages unchanged: transaction search and confirmation, Visa classification, card blocking, complaint filing, and CSAT. The voice module is untouched. Interactions, transcripts, surveys, and complaints are recorded with the `Web Chat` channel.
- **Decisions:** each turn goes first through Jev, with the same bounded questions and thresholds as calls. Then a schema-constrained LLM classifier (`ChatTurnInterpretation`) handles what a call's Realtime model handles: search filters and stage intents. State changes only for an allowed, non-`other` intent above the confidence gate. Prompt abuse is blocked on the single ingress before any branch runs. Human, restart, and cancel are handled before stage decisions.
- **Replies:** the greeting is deterministic. After that, each reply is generated in streaming from authoritative facts (the transaction, Visa code, complaint number) and a reference message: the voice templates or web-specific texts. If the model fails, or drops a required identifier such as the complaint number, the reference text replaces it.
- **Transaction context:** a `transaction_id` is used only when it belongs to the customer. Otherwise it is ignored without revealing whether it exists.
- **API:**
  - `POST /api/izzy/sessions` with `{transaction_id?, locale?}` opens a chat.
  - `POST /api/izzy/sessions/{id}/messages` with `{message}` returns `text/event-stream`, with `delta`, `replace`, `error`, `state`, and `done` events.

Limitations: chat sessions and LangGraph checkpoints live in process memory (`InMemorySaver`). They expire after `IZZY_CHAT_SESSION_TTL_MINUTES`, are lost on restart, and require a single server process. There is no live human handoff in the web chat; Izzy offers the phone line instead. Complaints are demo records and are never sent to Visa. Without `OPENAI_API_KEY`, the chat answers with an "unavailable" message that includes the phone number.

## Demo web login

The web interface offers two paths: a searchable synthetic-customer selector for judges and the original six-digit Factored ID login. Search is case- and accent-insensitive, duplicate names have a safe profile label, and the browser receives no document numbers in search results. The selected opaque value is signed, resolved to the customer document number server-side, and passed through the same Factored ID authentication method before the normal isolated customer session is created.

This shortcut is controlled impersonation for the hackathon demo, not production authentication. The selector searches the customers loaded by `dispute-db-seed-lakehouse` into PostgreSQL. The selected profile exposes a regional locale (`pt-BR`, `es-CO`, `es-MX`, `es-AR`, or `en-US`) for the interface-localization layer.

## Shady Business purchase simulator

Authenticated demo customers can open `/shop`, browse a humorous synthetic catalog, manage a browser-session cart, and pay with one of their active mock credit cards. The server resolves authoritative catalog prices, validates card ownership and status, and writes the approved purchase to the same PostgreSQL transactions table used by Factored Bank.

Every checkout also injects exactly one randomly selected training scenario: either a duplicate Shady Business charge or an unrelated high-value electronics transaction in a configured South Asian location. The receipt does not reveal the selected scenario; the judge discovers it in `/transactions` and can continue into the dispute journey. No real card network, merchant processor, money movement, inventory service, or production database is used; the PostgreSQL database is a local Docker container with synthetic data.

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

- every non-empty, size-valid customer message enters the same compiled graph and reaches its explicit abuse-screening node before any business-policy node;
- customer text is explicitly treated as untrusted data;
- the structured schema classifies prompt manipulation, hidden-instruction extraction, credential extraction, and unrelated-data access attempts in the same bounded LLM call;
- abuse blocking requires the `prompt_abuse` class and an abuse-confidence score of at least 0.80, reducing false positives on legitimate banking questions;
- inputs are limited to 500 characters and sessions default to 20 uncached LLM calls;
- repeated turns use a phase-and-locale-aware cache;
- unrelated requests receive a fixed scope response;
- generated answers are length-limited and rejected if they contain internal-instruction, credential, code-block, or URL markers;
- the model has no customer-database or tool access; and
- API errors or exhausted limits fail closed to the existing human-handoff path.

LangChain provides `@before_agent` and `@before_model` middleware decorators for agents created with its high-level `create_agent` API. This prototype uses a custom LangGraph `StateGraph`, so the explicit `screen_abuse` graph node performs the authoritative check exactly once and also protects direct compiled-graph invocation. No caller-provided flag can skip this node. This keeps the safety boundary inside the graph rather than relying on individual business branches or a no-op facade decorator.

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
