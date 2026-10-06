# Data Engineering

The lakehouse behind the Visa dispute prototype. It takes the synthetic bank data
that arrives as CSV files in an S3 bucket and turns it into clean, typed tables the
dispute agent can query.

All data here is **synthetic**. No real customer information appears in the source,
in the lakehouse, or in any example below.

---

## 1. What this folder is about

An agent handling a dispute needs answers fast: which card was charged, what the
customer bought, whether they've called before, what they said last time. Those
answers are spread across eight source files with different shapes, different
delivery schedules, and deliberately messy data — duplicate rows, impossible dates,
missing values.

This folder is the pipeline that makes those files usable, in three layers:

| Layer | Name | What's in it | Built by |
|---|---|---|---|
| 0 | **Copper** | Raw CSVs, exactly as the bucket delivered them | `bucket_download.py` |
| 1 | **Bronze** | Landing tables. Nothing thrown away, nothing changed | `dlt` |
| 2 | **Silver** | Typed, cleaned, deduplicated tables with history | `SQLMesh` |

Between bronze and silver there's a **quality gate**: Soda checks the rows that just
landed, and silver only runs if they pass.

```
  S3 bucket (CSV)
        │  bucket_download.py          ── optional: work from a local copy
        ▼
  0-copper/  <table>/year=/month=/day=/*.csv
        │  src/<table>/to_bronze.py    ── dlt: extract + load
        ▼
  bronze.<table>        (append-only, all text, full load lineage)
        │  soda contract verify        ── gate: stops the job before silver
        │  sqlmesh run
        ▼
  silver.<table>        (typed, deduplicated, with history — ready to query)
```

### The eight sources

They arrive in two shapes, and that difference drives everything else in this
folder — the tools, the models, and the commands.

**Facts** — one folder per day, new rows only:

- `transactions` — card and account movements (the dispute evidence)
- `call_center_interactions` — every contact with the call center
- `call_transcripts` — what was actually said on those calls
- `complaints` — formal cases, disputes included

**Snapshots** — the whole table re-sent every time:

- `customers` — cardholders (monthly)
- `products` — cards and accounts (monthly)
- `service_agents` — call center staff (monthly)
- `branches` — static reference data

A fact brings *new rows for a new day*. A snapshot brings *the entire table again*,
with no hint of what changed since last time. Working out what changed is the job
of the silver dimension models (§3).

---

## 2. The tools, and why

Four tools: **dlt**, **MotherDuck**, **SQLMesh**, and **Soda**. None of them needs a
cluster, a scheduler, or a warehouse running in the background. The pipeline is
plain Python and SQL, and the same code runs on a laptop and in CI.

### Loading the data — `dlt`

[`dlt`](https://dlthub.com/) is a library you import, not a platform you deploy. It
handles the fiddly parts of loading: working out the schema, packaging loads so a
failed run can resume, and stamping every row with where it came from.

What it gives us:

- **New columns don't break the pipeline.** Bronze is set to `evolve`
  ([`utils.py`](src/utils.py#L25-L29)), so an unexpected column just lands. It gets
  caught later at the quality gate, where someone can actually look at it.
- **Every row knows which run loaded it.** That single `_dlt_load_id` column does
  three jobs: it lets bronze safely keep every version of every day, it lets the
  quality gate check only the rows that just arrived, and it lets silver pick the
  newest version of a reloaded day.
- **A half-finished run can't quietly succeed.** If a run dies mid-load, the next
  one stops and says so instead of skipping the data and reporting success
  ([`utils.py`](src/utils.py#L409-L418)).
- **Parallelism is a few settings**, tuned per table
  ([`configure_dlt_parallelism`](src/utils.py#L104)).

Compared with Fivetran, Glue, or Airbyte: there's no service to deploy and no UI to
click through. Loading a table is one command, and the extraction logic is Python
in this repo that anyone can read in a pull request.

### Storage and compute — `MotherDuck`, with `DuckDB` compatibility

**MotherDuck** is the lakehouse. It's a hosted catalog the whole team and CI share,
reached with a token — no cluster to size, no warehouse to start, nothing to keep
running between loads. It's the default target for every command here.

The bonus is that MotherDuck speaks **DuckDB**, so the exact same code also runs
against a local DuckDB file. One [`--target`](src/utils.py#L64-L75) flag picks
where you're writing:

- **`motherduck`** → the shared `prod` catalog. The default.
- **`local`** → a DuckDB file on disk. No credentials, no network, handy for
  developing and testing.

The SQL is identical either way, so moving between them is a flag, not a rewrite.

What the engine does for us:

- **Reads the CSVs directly.** Extraction is a `READ_CSV` over a list of S3 paths
  with `HIVE_PARTITIONING=TRUE` — it parses the files and picks the date straight
  out of the folder names ([`extract_partition`](src/utils.py#L315)). No extra copy
  of the data.
- **Same credentials for S3 and local files.** Reads go through the same `fsspec`
  object that listed and hashed the files, so one setup covers `s3://…` and a local
  folder.
- **Big backfills stream.** A full-history load is one scan handed back in batches
  ([`extract_full_history`](src/utils.py#L257)), so the whole history never has to
  fit in memory.
- **Real geometry types.** The `spatial` extension gives `POINT_2D`, so transaction
  coordinates are a proper location in silver instead of two loose numbers.

### Transforming — `SQLMesh`

[`SQLMesh`](https://sqlmesh.com/) builds silver. Each model is a SQL file with a
header declaring its type, columns, and grain
([`sqlmesh/models/silver/`](sqlmesh/models/silver/)).

Why it fits this pipeline:

- **Incremental loading is one declaration.** `INCREMENTAL_BY_TIME_RANGE` on
  `process_date` with `lookback 3` is the whole specification
  ([`transactions.sql`](sqlmesh/models/silver/transactions.sql#L3-L6)). SQLMesh
  remembers which days it has already built and works out what's missing — no
  hand-written merge logic.
- **Column types are enforced.** The `COLUMNS (...)` block is a real contract:
  `DECIMAL(15,2)`, `VARCHAR(30) PRIMARY KEY`, `NOT NULL`. If a transformation stops
  producing a valid value, the model fails there.
- **Rebuilding a date range is a built-in command.** `sqlmesh plan -r <model>` wipes
  and rebuilds specific days. That's what makes late data manageable (§4).
- **You see the plan before it runs.** `sqlmesh plan dev` builds in a separate
  environment and shows exactly what will change and what will rebuild. Promoting to
  prod swaps views rather than rebuilding tables.
- **State is kept apart from data**, in its own `sqlmesh_state` catalog
  ([`config.yaml`](sqlmesh/config.yaml#L20-L24)), so the data can be dropped and
  rebuilt without losing the record of what was already built.
- **Shared SQL lives in macros.** `@LATEST_LOAD`, `@NORMALIZE_STRING`, and
  `@NOW_IN_BOGOTA_TZ` ([`macros/`](sqlmesh/macros/)) are written once and reused by
  every model.

Compared with dbt: dbt asks you to write and maintain the incremental logic
yourself, and it doesn't track which days have been built — so fixing a bad backfill
means scripting it. SQLMesh knows which days exist, which is exactly the problem
this pipeline has.

### Quality checks — `Soda`

[`Soda`](https://www.soda.io/) checks bronze **before** silver runs. One contract per
source in
[`src/<table>/data_contracts/to_silver.yml`](src/transactions/data_contracts/to_silver.yml),
with a config for each target ([`soda/`](soda/)).

The important detail is *what* gets checked. Each contract looks only at the rows
from the current run:

```yaml
variables:
  LOAD_IDS:
filter: "list_contains(string_split('${var.LOAD_IDS}', ','), _dlt_load_id)"
```

Bronze keeps every version of a reloaded day. Filtering by *date* would compare a
day against its own earlier copies and flag every row as a duplicate. Filtering by
*load id* checks exactly what just arrived. The `to_bronze` scripts print those ids
as `LOAD_IDS=…` and write them to `$GITHUB_OUTPUT`
([`emit_window_outputs`](src/utils.py#L370)), so the next step can use them directly.

Contracts cover unexpected columns, missing values, duplicates, allowed values,
text lengths, number ranges, formats, whether a value will convert to its silver
type, and whether dates make sense against each other.

Compared with dbt tests, which run *after* the transformation: by then a bad row is
already in silver. Soda runs against bronze as a gate, which is the point. And the
checks are YAML in git, so they show up in a pull request.

---

## 3. How the data is modelled

### Bronze: land everything, change nothing

Bronze reads every column as text. A malformed value *lands* instead of crashing the
load, and the quality gate then reports exactly which column and which rows are
wrong. Converting types here would turn a data quality finding into a crash with no
detail.

Every bronze row carries:

| Column | What it is |
|---|---|
| `_source_file` | The file the row came from |
| `_source_fingerprint` | MD5 of that file's contents (drives change detection) |
| `_processed_at` | When it was extracted |
| `_dlt_load_id` | Which run loaded it |
| `_dlt_id` | A stable per-row id (used to break ties consistently) |

Nothing in bronze is ever updated or deleted, so it's a replayable record of what
the source actually sent — and silver can always be rebuilt from it.

### Silver facts: build only the days that need it

`transactions`, `call_center_interactions`, and `call_transcripts` are
`INCREMENTAL_BY_TIME_RANGE` on `process_date` with `lookback 3`. Each run builds the
days in its range plus the last three, so a recent correction gets picked up on its
own.

`complaints` is different — `INCREMENTAL_BY_UNIQUE_KEY` on `complaint_id` — because a
complaint **changes over time**: created, assigned, responded to, resolved, closed.
Each delivery carries a further-along version of the same case. Keying on the id
means the latest version wins; keying on the date would leave five copies of one
case.

### Silver dimensions: building history from snapshots

This is the biggest piece of modelling here. `customers`, `products`, and
`service_agents` arrive as monthly photos with **no indication of what changed**. The
models work it out by comparing one photo to the next, producing a full history with
`valid_from`, `valid_to`, `is_current`, and `version_number`
([`customers.sql`](sqlmesh/models/silver/customers.sql)):

1. **Take the newest copy of each photo** — `@LATEST_LOAD`, so a re-sent photo
   replaces the earlier one.
2. **Convert and tidy** — `TRY_CAST` for types, `@NORMALIZE_STRING` (trim, uppercase,
   strip accents) for text, so `"Bogotá"` and `"BOGOTA "` become one value. This
   matters directly: the agent matches caller names against these fields, and an
   accent shouldn't split one customer into two.
3. **Flag impossible dates**, then clamp them for sorting — never drop them, never
   invent a replacement.
4. **Pick one row per customer per photo** — most trustworthy date first, with
   `_dlt_id` as the final tie-break so the same row wins every time.
5. **Compare attributes one by one** — a separate line per business column. It's
   verbose deliberately: adding or removing a column from the comparison is a single
   visible change in review. Timestamps and metadata are left out, so a touched
   `last_updated` alone never creates a bogus new version.
6. **Number the versions and close the date ranges.**

Validity follows the photo date, never `last_updated` — the photo date is the one
thing we know to be true. The exception: a customer's *first* version is backdated to
`last_updated` when that's earlier, so a long-standing customer doesn't look like
they joined on the day of the first delivery.

These models rebuild from all photos on every run, which makes the result
**order-independent** — photos can arrive out of order or be backfilled and the
history comes out the same. `branches` rebuilds too but has no history, being static
reference data.

### Conventions

- **Every model declares its grain**, so SQLMesh can reason about uniqueness.
- **Flag, don't drop.** `is_future_transaction`, `is_future_last_updated`,
  `has_duplicated_employee_code` — odd rows stay queryable and labelled. Quietly
  dropping dispute evidence would be the wrong call.
- **Lineage carries through.** `_source_file`, `_dlt_load_id`, and `_dlt_id` reach
  silver, so any row can be traced back to the file and run that produced it.

---

## 4. Duplicates, late data, and quality problems

### Duplicates

The source puts in about **2% duplicates** on purpose. Three things catch them:

| Level | How |
|---|---|
| File | `_source_fingerprint` — a file whose contents haven't changed is never reloaded |
| Load | The contract checks only this run's rows |
| Row | `QUALIFY ROW_NUMBER() OVER (PARTITION BY key ORDER BY …, _dlt_id) = 1` |

The row-level dedup is **deterministic**, which matters more than it sounds. The
sort always ends with `_dlt_id`, a value stored in bronze, so two runs over the same
data keep the *same* row. Breaking ties on something not stored — a row number, a
random value, the current time — would let silver change between runs with no change
in the source. A dispute answer that shifts when you re-run it isn't defensible.

For facts the newest transaction date wins; for dimensions the most trustworthy date
wins, with flagged rows last.

### Late-arriving data

Four things work together:

1. **Re-check recent days by content.** Every run re-examines a window of recent days
   (`--lookback-days`, default 3), hashes the source files, and compares against the
   hashes already in bronze ([`read_stored_fingerprints`](src/utils.py#L194)).
   Unchanged days print `SKIP`; changed days reload. Because it compares *contents*,
   a file rewritten with the same data is correctly left alone.
2. **No separate state to drift.** Those previous hashes come from bronze itself, so
   there's no tracking table to fall out of sync.
3. **Reloads append, silver takes the newest.** A reloaded day gets a new load id,
   bronze keeps both, and `@LATEST_LOAD` shows silver only the newest — so rows
   deleted upstream disappear from silver without anything being deleted from bronze.
4. **Models look back too.** `lookback 3` means a scheduled run rebuilds the last
   three days anyway.

For corrections **older** than that window, `to_bronze` prints the changed range
(`CHANGED_DATES`, `start_date`, `end_date`), which feeds a targeted rebuild (§6).

### Quality problems

The gate is firm: **if a contract fails, the job stops before silver runs.** Bronze
keeps the bad rows so you can look at them, and silver keeps its last good state.
Within a run:

- **Bronze** takes everything as text, so no value can crash the load.
- **The contract** says exactly what's wrong, and how serious it is.
- **Silver** enforces types, uses `TRY_CAST` so an unparseable value becomes `NULL`
  rather than an error, and flags anything questionable as a boolean column.

Known quirks of this synthetic source, all handled rather than hidden: ~2% duplicate
ids, future-dated timestamps, complaint dates out of order, `employee_code` reused
across different agents, and gaps in optional fields.

---

## 5. Why most checks warn instead of failing

Checks default to `warn`, with a specific set still blocking. One rule decides which:

> **A check fails the build when a bad row would break silver. It warns when silver
> already handles it.**

A failure stops the pipeline. Failing on something silver is built to absorb blocks
the team over a *known* property of the data and fixes nothing. The source
deliberately includes ~2% duplicates, so strict duplicate checks would have failed
essentially every run — and a gate that's always red gets ignored, or switched off.
At `warn` the signal stays visible and the pipeline keeps moving.

### What warns

**Missing values in optional columns** — `merchant_name`, `branch_id`, `fraud_score`,
`agent_id`, `subcategory`, `resolution_date`, and so on. Silver allows these to be
empty. A missing merchant name on an ATM withdrawal is correct, not broken. The
check stays so the *rate* is visible: missing merchants jumping from 3% to 60% is a
real signal even though no single row is wrong.

**Dates that don't line up** — `last_updated` after the photo date,
`registration_date` after `last_updated`, `transaction_date` after `process_date`,
first response after resolution. Silver flags these rows, clamps them for sorting,
and keeps them queryable. Already handled, and the flag is more useful than a
blocked pipeline.

**Duplicate keys** — `customer_id`, `document_number`, `product_id`. The ~2% rate is
a known property of the source and silver's deterministic dedup resolves it.
`service_agents.employee_code` warns for a different reason: it genuinely isn't a
key, since the same code gets reused across agents. Silver exposes
`has_duplicated_employee_code` rather than pretending otherwise.

### What still fails

These block, because silver can't produce a correct table without them:

- **Unexpected columns** — the source changed shape and someone needs to look.
- **Missing or duplicate primary keys** — `transaction_id`, `complaint_id`,
  `interaction_id`, `transcript_id`. Every downstream join depends on them, and an
  ambiguous key has no right answer.
- **Missing required columns** — `customer_id`, `amount`, `currency`,
  `transaction_status`, `process_date`. Silver requires them, so the model would fail
  anyway; failing at the gate gives a much clearer error.
- **Values that won't convert** — an amount that silently becomes `NULL` is the
  dangerous case. A dispute over an amount that quietly vanished is worse than a
  stopped pipeline.
- **Unexpected values in fixed sets** — `transaction_type`, `currency`, `channel`,
  `transaction_status`, `transaction_country`. A new value means a new business case
  the downstream logic has never seen.
- **Out-of-range numbers and over-long text** — `fraud_score` 0–100, latitude ±90,
  longitude ±180, and lengths matching silver. An over-long value would get truncated.
- **More than one photo in a single load** — this would scramble the version
  ordering in the dimension history, which can't be fixed without reloading.

A control is never relaxed just to make a scenario pass. Each `warn` above points at
specific silver logic that handles the case — that code is the justification.

---

## 6. Commands

### Setup

```bash
cd visa-dispute-hackathon/data_engineering
uv sync                                   # install dependencies
cp .env.example .env                      # then fill it in
```

`.env` (don't commit it — it's already in `.gitignore`):

```bash
FACTORED_BUCKET_NAME=...                  # S3 source
FACTORED_REGION=...
FACTORED_ACCESS_KEY_ID=...
FACTORED_SECRET_ACCESS_KEY=...

MOTHERDUCK_LAKEHOUSE_TOKEN=...
LAKEHOUSE_LOCAL_PATH=lakehouse/lakehouse.duckdb   # only for --target local
```

Create the catalogs, then optionally pull copper down:

```bash
uv run python -m src.motherduck_setup     # prod + sqlmesh_state in MotherDuck
uv run python -m src.local_duckdb_setup   # same schemas in a local DuckDB file

uv run python -m src.bucket_download      # S3 -> lakehouse/0-copper (skips existing)
```

`bucket_download` is optional — `--copper-root` takes an `s3://…` URL, so bronze can
load straight from the bucket.

Every command below runs from this folder (`data_engineering/`) — no `cd` into
`sqlmesh/`. SQLMesh calls pass `--dotenv .env -p sqlmesh/` to point at the project
and load credentials, plus an explicit `--gateway`:

- `--gateway motherduck` → the shared `prod` catalog
- `--gateway local` → a local DuckDB file

For the loaders, `--target motherduck` is the default; add `--target local` to write
to the DuckDB file instead.

### First load (full)

Facts load their whole history in one scan and one run. The command **refuses** if
bronze already holds days in that range, since reloading would duplicate them — use
the incremental load for days already in.

```bash
# One command per fact table — entire history
uv run python -m src.transactions.to_bronze --full-load
uv run python -m src.call_center_interactions.to_bronze --full-load
uv run python -m src.call_transcripts.to_bronze --full-load
uv run python -m src.complaints.to_bronze --full-load

# Stop at a given day
uv run python -m src.transactions.to_bronze --full-load --process-date 2026-06-17

# Straight from S3, no local copy
uv run python -m src.transactions.to_bronze --full-load \
  --copper-root s3://$FACTORED_BUCKET_NAME/data
```

Snapshots carry no date in the file, so you pass the date of the photo (last day of
the month for a monthly delivery). `branches` is static and needs none.

```bash
uv run python -m src.customers.to_bronze      --snapshot-date 2026-06-17
uv run python -m src.products.to_bronze       --snapshot-date 2026-06-17
uv run python -m src.service_agents.to_bronze --snapshot-date 2026-06-17
uv run python -m src.branches.to_bronze
```

Each run prints `LOAD_ID=…` (or `LOAD_IDS=…`). Pass that to the quality gate:

```bash
uv run soda contract verify \
  -c src/transactions/data_contracts/to_silver.yml \
  -ds soda/ds_config_motherduck_lakehouse.yml \
  --set LOAD_IDS=<load ids from the run>
```

Use `soda/ds_config_local_lakehouse.yml` when the target was local.

Then build silver, one model at a time with `--select-model`. `--execution-time`
pins "now" to the day you're loading, so the models don't try to build days that
have no data yet. `--auto-apply` skips the confirmation prompt.

Facts first:

```bash
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.transactions \
  --execution-time 2026-06-18 \
  --auto-apply

uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.call_center_interactions \
  --execution-time 2026-06-18 \
  --auto-apply

uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.call_transcripts \
  --execution-time 2026-06-18 \
  --auto-apply

uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.complaints \
  --execution-time 2026-06-18 \
  --auto-apply
```

Then the dimensions. These rebuild from all photos, so they need no date:

```bash
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan --select-model silver.customers
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan --select-model silver.products
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan --select-model silver.service_agents
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan --select-model silver.branches
```

Swap `--gateway motherduck` for `--gateway local` to build against the DuckDB file.

> **Always use `--select-model`.** The first positional argument to `plan` is an
> *environment* name, not a model. `plan silver.customers` doesn't plan that model —
> it creates an environment called `silver_customers` and materializes every model
> into its own suffixed schema. Your `prod` is untouched, but you get a stray
> environment. To clean one up:
>
> ```bash
> uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck invalidate silver_customers
> uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck janitor
> ```
>
> `invalidate` marks it for deletion; `janitor` drops the schema and tables.

### Incremental load

The normal mode for facts. It re-checks recent days, hashes the files, and loads only
the days whose contents actually changed — which is also how late corrections inside
the window get picked up.

```bash
# Default 3-day window
uv run python -m src.transactions.to_bronze --process-date 2026-06-17

# Wider window for a late correction
uv run python -m src.transactions.to_bronze --process-date 2026-06-17 --lookback-days 14

# Smaller batches if memory is tight
uv run python -m src.transactions.to_bronze --process-date 2026-06-17 --batch-days 30
```

Unchanged days print `SKIP <date> (unchanged)`; if nothing changed, nothing loads.
The run prints `CHANGED_DATES`, `LOAD_IDS`, `start_date`, and `end_date` for the next
step.

Snapshots have no incremental mode — each delivery is a new full photo, loaded with
the command above and a new `--snapshot-date`. Silver rebuilds the history from all
photos.

Run the quality gate with the printed `LOAD_IDS`, then build silver with `run`:

```bash
# One model, up to a given day
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway local run \
  --select-model silver.transactions --end "2026-06-17"

# Everything that's due
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck run
```

`run` builds missing or due days without touching model code. Use `plan` when the
*SQL has changed* — it shows the diff and asks before rebuilding.

### Restating a model

Two different situations, two different commands:

**The SQL changed** — `plan` picks up the new code and rebuilds what it affects:

```bash
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.customers
```

**The data changed** — add `--restate-model` to wipe the stored days and rebuild
them from bronze, even though the SQL is identical:

```bash
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.customers \
  --restate-model silver.customers
```

For a fact, narrow it to the days that changed — `to_bronze` printed them as
`start_date` and `end_date`:

```bash
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck plan \
  --select-model silver.transactions \
  --restate-model silver.transactions \
  -s "$start_date" -e "$end_date"
```

This is what you reach for when a correction arrives older than the lookback window,
or after fixing logic that produced wrong values in days already built. Restating a
model also restates anything built from it, which is intended — a corrected
transaction should flow through.

Handy alongside:

```bash
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck check_intervals
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck fetchdf \
  "SELECT * FROM silver.transactions LIMIT 5"
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck audit \
  --model silver.transactions
uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck environments
```

### End to end, one day

```bash
uv run python -m src.transactions.to_bronze --process-date 2026-06-17
# note the LOAD_IDS=... line

uv run soda contract verify \
  -c src/transactions/data_contracts/to_silver.yml \
  -ds soda/ds_config_motherduck_lakehouse.yml \
  --set LOAD_IDS=<load ids>
# stop here if it fails — don't build silver on rejected data

uv run sqlmesh --dotenv .env -p sqlmesh/ --gateway motherduck run \
  --select-model silver.transactions --end "2026-06-17"
```