import hashlib
import os
from collections.abc import Generator
from datetime import date, timedelta
from pathlib import Path

import click
import dlt
import duckdb
import fsspec
import pyarrow as pa
from dlt.common.destination import Destination
from dotenv import load_dotenv
from pyarrow import Table as ArrowTable

# src/utils.py -> the project root is one level above src/
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load .env once here so every to_bronze script gets the same environment
load_dotenv(PROJECT_ROOT / ".env")

MOTHERDUCK_CATALOG = "prod"

# Shared schema contract: let bronze absorb upstream schema drift
BRONZE_SCHEMA_CONTRACT = {
    "tables": "evolve",
    "columns": "evolve",
    "data_type": "evolve",
}

# Common DuckDB READ_CSV arguments: everything as VARCHAR, carry the source filename
READ_CSV_BASE_ARGS = "ALL_VARCHAR=TRUE, FILENAME=TRUE, SEP=',', UNION_BY_NAME=TRUE"

# Parquet keeps the Arrow types dlt inferred on the way to bronze
BRONZE_LOADER_FILE_FORMAT = "parquet"

# Copper -> bronze CLI defaults, shared by every to_bronze command
DEFAULT_COPPER_ROOT = "lakehouse/0-copper"
DEFAULT_LOOKBACK_DAYS = 3
# Days per dlt run in replay mode: few runs (fast) without holding the whole
# history in one package (memory, and a failure only costs one batch)
DEFAULT_BATCH_DAYS = 100

# A partition ready to load: (folder date, file paths, fingerprint per file name)
Partition = tuple[date, list[str], dict[str, str]]


def resolve_project_path(path: str) -> str:
    # Relative paths from .env or CLI options are taken from the project root, not
    # from the directory the command happens to be run from. URLs pass through.
    if "://" in path:
        return path
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return str(candidate)


def lakehouse_local_path() -> str:
    # Single source for the local DuckDB file location
    return resolve_project_path(os.environ["LAKEHOUSE_LOCAL_PATH"])


def build_destination(target: str) -> Destination:
    # "motherduck" writes to the cloud catalog, "local" writes to the local DuckDB file
    if target == "motherduck":
        return dlt.destinations.motherduck(
            credentials={
                "database": MOTHERDUCK_CATALOG,
                "password": os.environ["MOTHERDUCK_LAKEHOUSE_TOKEN"],
            }
        )
    if target == "local":
        return dlt.destinations.duckdb(lakehouse_local_path())
    raise ValueError(f"Unknown target: {target}")


def connect_lakehouse(target: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    # Read-side counterpart of build_destination: the same two targets, for querying
    if target == "motherduck":
        return duckdb.connect(
            database=f"md:{MOTHERDUCK_CATALOG}",
            read_only=read_only,
            config={"motherduck_token": os.environ["MOTHERDUCK_LAKEHOUSE_TOKEN"]},
        )
    if target == "local":
        return duckdb.connect(database=lakehouse_local_path(), read_only=read_only)
    raise ValueError(f"Unknown target: {target}")


def lakehouse_exists(target: str) -> bool:
    # A local lakehouse that was never created cannot be opened read-only
    if target == "local":
        return os.path.exists(lakehouse_local_path())
    return True


def checkpoint_duckdb(database_path: str) -> None:
    # Flush and consolidate WAL file into the main database file
    with duckdb.connect(database=database_path) as connection:
        connection.execute("CHECKPOINT;")


def configure_dlt_parallelism(
    workers: int = 3,
    max_parallel_items: int = 3,
    normalize_workers: int = 1,
) -> None:
    # Inject dlt load_id and dlt_id into the PyArrow tables during normalization
    os.environ["NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_LOAD_ID"] = "True"
    os.environ["NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_ID"] = "True"
    # File rotation: split extracted/normalized data into chunks
    os.environ["SOURCES__DATA_WRITER__FILE_MAX_ITEMS"] = "100000"
    os.environ["NORMALIZE__DATA_WRITER__FILE_MAX_ITEMS"] = "100000"
    # Parallelism across the three dlt stages
    os.environ["EXTRACT__WORKERS"] = str(workers)
    os.environ["EXTRACT__MAX_PARALLEL_ITEMS"] = str(max_parallel_items)
    # Normalize runs in-process by default. With more than one worker dlt starts
    # a process pool; on Linux each process is forked (copied) from the main one,
    # and a large main process fails with "Cannot allocate memory". "spawn" starts
    # each worker as a fresh interpreter instead, so it copies nothing. It needs
    # the script's `if __name__ == "__main__":` guard, which every to_bronze has.
    os.environ["NORMALIZE__WORKERS"] = str(normalize_workers)
    if normalize_workers > 1:
        os.environ["NORMALIZE__START_METHOD"] = "spawn"
    os.environ["LOAD__WORKERS"] = str(workers)


def extract_snapshot(
    file_pattern: str,
    extra_columns: dict[str, str] | None = None,
) -> Generator[ArrowTable, None, None]:
    # Full-snapshot extraction for non-partitioned resources (customers, products)
    # extra_columns maps a column name to a trusted SQL expression (e.g. {"snapshot_ts": "'2026-07-31'::DATE"})
    extra_select = "".join(
        f",\n            {expression} AS {name}"
        for name, expression in (extra_columns or {}).items()
    )
    with duckdb.connect(database=":memory:") as connection:
        sql_query = f"""
        SELECT
            * RENAME (filename AS _source_file){extra_select},
            CURRENT_TIMESTAMP AS _processed_at
        FROM READ_CSV('{file_pattern}', {READ_CSV_BASE_ARGS}, HIVE_PARTITIONING=FALSE)
        """
        yield connection.sql(sql_query).arrow()


# ---------------------------------------------------------------------------
# Daily-partitioned fact tables: window, fingerprints and per-partition extract
# ---------------------------------------------------------------------------


def build_window(end_date: date, lookback_days: int) -> list[date]:
    # Inclusive window [end_date - lookback_days, end_date], oldest first
    return [end_date - timedelta(days=offset) for offset in range(lookback_days, -1, -1)]


def list_partition_folders(filesystem, table_root: str) -> dict[date, str]:
    # Map each partition date to its folder, reading year/month/day from the path
    # itself, so it works with "year=2026/month=06/day=17" and with "2026/06/17"
    folders: dict[date, str] = {}

    for folder in filesystem.glob(f"{table_root}/*/*/*"):
        segments = folder.rstrip("/").split("/")[-3:]
        values = [segment.split("=")[-1] for segment in segments]

        if not all(value.isdigit() for value in values):
            continue

        year, month, day = (int(value) for value in values)
        folders[date(year, month, day)] = folder

    return folders


def folder_fingerprint(filesystem, folder: str) -> dict[str, str]:
    # Content hash per file: identical bytes always give the same value, so a
    # partition rewritten with the same content is still recognized as unchanged.
    # Keyed by base name so the value stays comparable if the copper root moves.
    fingerprints: dict[str, str] = {}

    for file_path in filesystem.glob(f"{folder}/*.csv"):
        with filesystem.open(file_path, "rb") as source_file:
            fingerprints[os.path.basename(file_path)] = hashlib.file_digest(
                source_file, "md5"
            ).hexdigest()

    return fingerprints


def read_stored_fingerprints(
    bronze_table: str, window: list[date], target: str = "motherduck"
) -> dict[date, dict[str, str]]:
    # Previous fingerprints come from bronze itself, taken from the newest load of
    # each partition. No separate state table is needed.
    stored: dict[date, dict[str, str]] = {}

    if not lakehouse_exists(target):
        # Very first run: the lakehouse has not been created yet
        return stored

    sql_query = f"""
    WITH latest_loads AS (
        SELECT
            process_date,
            MAX(_dlt_load_id::DOUBLE) AS load_id
        FROM {bronze_table}
        WHERE process_date BETWEEN $start_date::DATE AND $end_date::DATE
        GROUP BY process_date
    )
    SELECT
        bronze_rows.process_date,
        bronze_rows._source_file,
        ANY_VALUE(bronze_rows._source_fingerprint) AS fingerprint
    FROM {bronze_table} AS bronze_rows
    JOIN latest_loads
        ON bronze_rows.process_date = latest_loads.process_date
        AND bronze_rows._dlt_load_id::DOUBLE = latest_loads.load_id
    GROUP BY bronze_rows.process_date, bronze_rows._source_file
    """

    with connect_lakehouse(target, read_only=True) as connection:
        try:
            rows = connection.execute(
                sql_query, {"start_date": window[0], "end_date": window[-1]}
            ).fetchall()
        except duckdb.CatalogException:
            # The bronze table does not exist yet
            return stored

    for process_date, source_file, fingerprint in rows:
        stored.setdefault(process_date, {})[os.path.basename(source_file)] = fingerprint

    return stored


def is_local_filesystem(filesystem) -> bool:
    # fsspec reports the protocol as a string or a tuple depending on the backend
    protocols = (
        (filesystem.protocol,) if isinstance(filesystem.protocol, str) else filesystem.protocol
    )
    return "file" in protocols


def duckdb_readable_paths(filesystem, file_paths: list[str]) -> list[str]:
    # glob on a remote filesystem returns paths without the protocol, which DuckDB
    # cannot resolve. Restore the prefix and let DuckDB read through the same
    # filesystem object, so the credentials are configured only once.
    if is_local_filesystem(filesystem):
        return list(file_paths)
    return [filesystem.unstrip_protocol(file_path) for file_path in file_paths]


def extract_full_history(
    filesystem,
    partitions: list[Partition],
    rows_per_batch: int = 500_000,
) -> Generator[pa.RecordBatch, None, None]:
    # Backfill counterpart of extract_partition: every partition in one READ_CSV,
    # streamed in record batches so the whole history is never held in memory.
    # Output columns match extract_partition, so both modes write the same table
    # and the daily replay recognizes backfilled days as unchanged.
    is_local = is_local_filesystem(filesystem)

    source_paths: list[str] = []
    partition_dates: list[date] = []
    file_fingerprints: list[str] = []

    for partition_date, file_paths, fingerprints in partitions:
        readable_paths = duckdb_readable_paths(filesystem, file_paths)
        for file_path, readable_path in zip(file_paths, readable_paths, strict=True):
            source_paths.append(readable_path)
            partition_dates.append(partition_date)
            file_fingerprints.append(fingerprints[os.path.basename(file_path)])

    print(
        f"Extracting {len(source_paths)} file(s) across {len(partitions)} "
        "partition(s) in a single scan..."
    )

    # Lookup table: the full path DuckDB reports in `filename` -> folder date and hash
    file_map = pa.table(
        {
            "source_path": source_paths,
            "partition_date": pa.array(partition_dates, type=pa.date32()),
            "fingerprint": file_fingerprints,
        }
    )
    file_list = ", ".join(f"'{source_path}'" for source_path in source_paths)

    sql_query = f"""
    SELECT
        csv_rows.* EXCLUDE (process_date, year, month, day, filename),
        csv_rows.filename AS _source_file,
        csv_rows.process_date::DATE AS process_date,
        file_map.fingerprint AS _source_fingerprint,
        CURRENT_TIMESTAMP AS _processed_at
    FROM READ_CSV([{file_list}], {READ_CSV_BASE_ARGS}, HIVE_PARTITIONING=TRUE) AS csv_rows
    JOIN file_map
        ON csv_rows.filename = file_map.source_path
    """

    with duckdb.connect(database=":memory:") as connection:
        if not is_local:
            connection.register_filesystem(filesystem)
        connection.register("file_map", file_map)
        reader = connection.execute(sql_query).fetch_record_batch(rows_per_batch)
        yield from reader


def extract_partition(
    filesystem,
    partition_date: date,
    file_paths: list[str],
    fingerprints: dict[str, str],
) -> Generator[ArrowTable, None, None]:
    # One partition of a daily fact table. process_date is read directly
    # from the column.
    print(f"Extracting {len(file_paths)} file(s) for {partition_date}...")

    is_local = is_local_filesystem(filesystem)
    file_paths = duckdb_readable_paths(filesystem, file_paths)

    file_list = ", ".join(f"'{file_path}'" for file_path in file_paths)
    fingerprint_cases = " ".join(
        f"WHEN '{file_name}' THEN '{fingerprint}'"
        for file_name, fingerprint in fingerprints.items()
    )

    # HIVE_PARTITIONING=TRUE: DuckDB infers year/month/day columns from the folder
    # path; they are dropped as redundant since process_date is read directly
    sql_query = f"""
    SELECT
        * EXCLUDE (process_date, year, month, day, filename),
        filename AS _source_file,
        process_date::DATE AS process_date,
        CASE REGEXP_EXTRACT(filename, '[^/]+$')
            {fingerprint_cases}
        END AS _source_fingerprint,
        CURRENT_TIMESTAMP AS _processed_at
    FROM READ_CSV([{file_list}], {READ_CSV_BASE_ARGS}, HIVE_PARTITIONING=TRUE)
    """

    with duckdb.connect(database=":memory:") as connection:
        if not is_local:
            connection.register_filesystem(filesystem)
        # fetch_arrow_table returns a Table; .arrow() returns a reader in recent DuckDB
        yield connection.execute(sql_query).fetch_arrow_table()


def emit_load_id(load_info: dlt.common.pipeline.LoadInfo) -> str:
    # Print the load id in a machine-readable line and expose it to the next GitHub Actions step
    load_ids = load_info.loads_ids
    if len(load_ids) != 1:
        raise RuntimeError(f"Expected exactly one load id, got: {load_ids}")
    load_id = load_ids[0]

    print(f"LOAD_ID={load_id}")
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as output_file:
            output_file.write(f"load_id={load_id}\n")
    return load_id


def emit_window_outputs(changed_dates: list[date], load_ids: list[str]) -> None:
    # Window counterpart of emit_load_id: hand the whole changed range to the next
    # workflow steps, so silver can be restated over exactly those days
    changed_csv = ",".join(str(day) for day in changed_dates)
    load_ids_csv = ",".join(load_ids)

    print(f"CHANGED_DATES={changed_csv}")
    print(f"LOAD_IDS={load_ids_csv}")

    github_output = os.getenv("GITHUB_OUTPUT")
    if not github_output:
        return

    with open(github_output, "a") as output_file:
        output_file.write(f"changed_dates={changed_csv}\n")
        output_file.write(f"load_ids={load_ids_csv}\n")
        if changed_dates:
            output_file.write(f"start_date={min(changed_dates)}\n")
            output_file.write(f"end_date={max(changed_dates)}\n")


def run_copper_to_bronze(
    resource: dlt.sources.DltResource,
    resource_name: str,
    target: str = "motherduck",
    checkpoint: bool = True,
) -> dlt.common.pipeline.LoadInfo:
    # Standardized pipeline build + run for every Copper -> Bronze transfer
    # Separate pipeline name per cloud target so each destination keeps its own state
    pipeline_suffix = "" if target == "local" else f"-{target}"

    pipeline_name = f"{resource_name}_copper-bronze{pipeline_suffix}"
    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=build_destination(target),
        dataset_name="bronze",
        progress="log",
    )

    if pipeline.has_pending_data:
        # A previous run failed after extracting. dlt would finish that package
        # and silently ignore the data passed now, so the caller would report
        # partitions as loaded that were not. Stop and let a person decide.
        raise RuntimeError(
            f"Pipeline '{pipeline_name}' has pending packages from a failed run. "
            "dlt would ignore the new data. Inspect them with "
            f"'uv run dlt pipeline {pipeline_name} info', then cancel them with "
            f"'uv run dlt -y pipeline {pipeline_name} abort-packages' and run again."
        )

    print(f"Starting data transfer: Copper -> Bronze ({resource_name.title()})...")
    load_info = pipeline.run(
        resource,
        loader_file_format=BRONZE_LOADER_FILE_FORMAT,
        schema_contract=BRONZE_SCHEMA_CONTRACT,
    )
    print(load_info)
    print("Transfer complete: Data successfully appended to Bronze layer.")

    # Force checkpoint to close and remove the WAL file (only applies to the local
    # file). Callers that run several partitions in a row checkpoint once at the end.
    if target == "local" and checkpoint:
        checkpoint_duckdb(lakehouse_local_path())
        print("DuckDB checkpoint executed successfully.")

    return load_info


# ---------------------------------------------------------------------------
# Copper -> bronze CLI factories
#
# Two shapes of resource, two factories:
#   - build_partitioned_bronze_command: daily-partitioned facts (transactions,
#     call_center_interactions, complaints). Replay window + fingerprints.
#   - build_snapshot_bronze_command: dimensions delivered as a full photo
#     (customers, products, branches). One snapshot date stamped per load.
# ---------------------------------------------------------------------------


def build_bronze_resources(resource_name: str):
    # dlt needs the table name at decoration time, so the resources are built per
    # dataset instead of being shared module-level functions
    @dlt.resource(name=resource_name, write_disposition="append")
    def extract_copper_replay(filesystem, partitions: list[Partition]):
        # Replay mode: several partitions go into a single dlt run, so the run
        # overhead is paid once per batch instead of once per day. Each partition
        # is still read on its own and keeps its own process_date and fingerprint.
        for partition_date, file_paths, fingerprints in partitions:
            yield from extract_partition(filesystem, partition_date, file_paths, fingerprints)

    @dlt.resource(name=resource_name, write_disposition="append")
    def extract_copper_history(filesystem, partitions: list[Partition]):
        # Full-load mode: every partition in one scan and one dlt run (one load_id)
        yield from extract_full_history(filesystem, partitions)

    return extract_copper_replay, extract_copper_history


def fingerprint_partition(filesystem, partition_date: date, folder: str) -> Partition | None:
    # Hash the folder's files; None when the folder has nothing to load
    fingerprints = folder_fingerprint(filesystem, folder)
    if not fingerprints:
        print(f"WARNING {partition_date}: folder has no CSV files, skipping")
        return None
    file_paths = [f"{folder.rstrip('/')}/{file_name}" for file_name in fingerprints]
    return partition_date, file_paths, fingerprints


def run_bronze_full_load(
    filesystem,
    partition_folders: dict[date, str],
    end_date: date | None,
    target: str,
    resource_name: str,
    history_resource,
) -> None:
    # Load the whole history (optionally up to end_date) in a single dlt run
    bronze_table = f"bronze.{resource_name}"

    selected_dates = sorted(
        partition_date
        for partition_date in partition_folders
        if end_date is None or partition_date <= end_date
    )
    if not selected_dates:
        raise click.ClickException(f"No partitions on or before {end_date}.")

    print(
        f"Full load: {selected_dates[0]} to {selected_dates[-1]} ({len(selected_dates)} partitions)"
    )

    # Guard: bronze is append-only, so loading days it already holds would
    # duplicate them. The daily replay is the tool for days already in bronze.
    full_window = build_window(selected_dates[-1], (selected_dates[-1] - selected_dates[0]).days)
    already_loaded = read_stored_fingerprints(bronze_table, full_window, target)
    if already_loaded:
        raise click.ClickException(
            f"{bronze_table} already holds {len(already_loaded)} day(s) in this range "
            f"({min(already_loaded)} to {max(already_loaded)}). Drop them first or "
            "use the daily replay (without --full-load)."
        )

    partitions = []
    for partition_date in selected_dates:
        partition = fingerprint_partition(
            filesystem, partition_date, partition_folders[partition_date]
        )
        if partition is not None:
            partitions.append(partition)

    if not partitions:
        raise click.ClickException("Every selected partition folder is empty.")

    load_info = run_copper_to_bronze(
        history_resource(filesystem, partitions),
        resource_name,
        target,
    )
    load_id = emit_load_id(load_info)
    emit_window_outputs([partition_date for partition_date, _, _ in partitions], [load_id])


def run_bronze_replay(
    filesystem,
    partition_folders: dict[date, str],
    end_date: date,
    lookback_days: int,
    batch_days: int,
    target: str,
    resource_name: str,
    replay_resource,
) -> None:
    # Re-check the window day by day and load only partitions whose files changed
    bronze_table = f"bronze.{resource_name}"

    window = build_window(end_date, lookback_days)
    print(f"Window: {window[0]} to {window[-1]} (inclusive)")

    stored_fingerprints = read_stored_fingerprints(bronze_table, window, target)

    pending_partitions = []

    for partition_date in window:
        folder = partition_folders.get(partition_date)

        if folder is None:
            print(f"WARNING {partition_date}: partition missing at source, skipping")
            continue

        partition = fingerprint_partition(filesystem, partition_date, folder)
        if partition is None:
            continue

        if partition[2] == stored_fingerprints.get(partition_date):
            print(f"SKIP {partition_date} (unchanged)")
            continue

        pending_partitions.append(partition)

    changed_dates = [partition_date for partition_date, _, _ in pending_partitions]

    if not pending_partitions:
        print("Nothing to load: every partition in the window is unchanged.")
        emit_window_outputs(changed_dates, [])
        return

    batches = [
        pending_partitions[start : start + batch_days]
        for start in range(0, len(pending_partitions), batch_days)
    ]
    print(
        f"Loading {len(pending_partitions)} changed partition(s) "
        f"in {len(batches)} run(s) of up to {batch_days} day(s)..."
    )

    load_ids = []
    for batch_number, batch in enumerate(batches, start=1):
        print(f"Batch {batch_number}/{len(batches)}: {batch[0][0]} to {batch[-1][0]}")
        load_info = run_copper_to_bronze(
            replay_resource(filesystem, batch),
            resource_name,
            target,
        )
        load_ids.extend(load_info.loads_ids)

    emit_window_outputs(changed_dates, load_ids)


def build_partitioned_bronze_command(
    resource_name: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    batch_days: int = DEFAULT_BATCH_DAYS,
    workers: int = 5,
    max_parallel_items: int = 10,
) -> click.Command:
    # Build the copper -> bronze CLI for one daily-partitioned fact. Every
    # to_bronze.py script of a fact is a call to this factory with its name.
    configure_dlt_parallelism(workers=workers, max_parallel_items=max_parallel_items)
    replay_resource, history_resource = build_bronze_resources(resource_name)

    # Defaults captured here, so the inner option names can shadow them safely
    default_lookback_days = lookback_days
    default_batch_days = batch_days

    @click.command()
    @click.option(
        "--process-date",
        type=click.DateTime(formats=["%Y-%m-%d"]),
        default=None,
        help=(
            "Most recent day to process. Required for the daily replay; "
            "with --full-load it is an optional upper bound."
        ),
    )
    @click.option(
        "--lookback-days",
        type=click.IntRange(min=0),
        default=default_lookback_days,
        show_default=True,
        help="Replay only: how many earlier days to re-check for late-arriving changes.",
    )
    @click.option(
        "--full-load",
        is_flag=True,
        default=False,
        help=(
            "Load every partition (up to --process-date, if given) in a single scan "
            "and a single dlt run. Refuses days already in bronze."
        ),
    )
    @click.option(
        "--copper-root",
        default=lambda: os.getenv("COPPER_ROOT", DEFAULT_COPPER_ROOT),
        show_default=DEFAULT_COPPER_ROOT,
        help="Copper location: a bucket URL or a path on disk.",
    )
    @click.option(
        "--batch-days",
        type=click.IntRange(min=1),
        default=default_batch_days,
        show_default=True,
        help="Replay only: changed days loaded per dlt run. Lower it if memory runs out.",
    )
    @click.option(
        "--target",
        type=click.Choice(["motherduck", "local"]),
        default="motherduck",
        show_default=True,
        help="Destination for the bronze layer.",
    )
    def main(
        process_date: click.DateTime | None,
        lookback_days: int,
        full_load: bool,
        copper_root: str,
        batch_days: int,
        target: str,
    ) -> None:
        if process_date is None and not full_load:
            raise click.UsageError("--process-date is required unless --full-load is set.")

        end_date = process_date.date() if process_date is not None else None

        if target == "local":
            print(f"Destination: {lakehouse_local_path()}")

        filesystem, resolved_root = fsspec.core.url_to_fs(resolve_project_path(copper_root))
        table_root = f"{resolved_root.rstrip('/')}/{resource_name}"

        partition_folders = list_partition_folders(filesystem, table_root)

        if not partition_folders:
            # Nothing at all under the root means a wrong path, not missing days
            raise click.ClickException(
                f"No partitions found under {table_root}. "
                "Check --copper-root (or COPPER_ROOT); relative paths are resolved "
                "from the project root."
            )

        print(
            f"Source: {table_root} "
            f"({len(partition_folders)} partitions, "
            f"{min(partition_folders)} to {max(partition_folders)})"
        )

        if full_load:
            run_bronze_full_load(
                filesystem,
                partition_folders,
                end_date,
                target,
                resource_name,
                history_resource,
            )
        else:
            run_bronze_replay(
                filesystem,
                partition_folders,
                end_date,
                lookback_days,
                batch_days,
                target,
                resource_name,
                replay_resource,
            )

    return main


def build_snapshot_bronze_command(
    resource_name: str,
    snapshot_column: str = "snapshot_ts",
    snapshot_date_help: str = (
        "Business date of the delivered photo (YYYY-MM-DD, last day of the month "
        "for a monthly delivery)."
    ),
    workers: int = 3,
    max_parallel_items: int = 3,
) -> click.Command:
    # Build the copper -> bronze CLI for one dimension delivered as a full photo.
    # The source carries no snapshot date, so the business date comes from the CLI
    # and is stamped as snapshot_column. Set snapshot_column to None for a
    # dimension that needs no date (static reference data).
    configure_dlt_parallelism(workers=workers, max_parallel_items=max_parallel_items)

    # dlt needs the table name at decoration time, so the resource is built here
    @dlt.resource(name=resource_name, write_disposition="append")
    def extract_copper_snapshot(
        file_pattern: str, snapshot_date: str | None
    ) -> Generator[ArrowTable, None, None]:
        # last_updated is a record timestamp, not the date of the photo, so the
        # business date comes from the CLI
        extra_columns = (
            {snapshot_column: f"'{snapshot_date}'::DATE"}
            if snapshot_column and snapshot_date
            else None
        )
        yield from extract_snapshot(file_pattern, extra_columns=extra_columns)

    @click.command()
    @click.option(
        "--snapshot-date",
        type=click.DateTime(formats=["%Y-%m-%d"]),
        required=snapshot_column is not None,
        default=None,
        help=snapshot_date_help,
    )
    @click.option(
        "--copper-root",
        default=lambda: os.getenv("COPPER_ROOT", DEFAULT_COPPER_ROOT),
        show_default=DEFAULT_COPPER_ROOT,
        help="Copper location: a bucket URL or a path on disk.",
    )
    @click.option(
        "--target",
        type=click.Choice(["motherduck", "local"]),
        default="motherduck",
        show_default=True,
        help="Destination for the bronze layer.",
    )
    def main(
        snapshot_date: click.DateTime | None,
        copper_root: str,
        target: str,
    ) -> None:
        # click already validated the format; isoformat() guarantees a safe
        # YYYY-MM-DD string for the extraction query
        snapshot_date_str = snapshot_date.date().isoformat() if snapshot_date else None
        print(f"Snapshot date: {snapshot_date_str} | Target: {target}")

        if target == "local":
            print(f"Destination: {lakehouse_local_path()}")

        # Path pattern anchored to the project root, not the cwd
        file_pattern = f"{resolve_project_path(copper_root).rstrip('/')}/{resource_name}/*.csv"
        print(f"Source: {file_pattern}")

        load_info = run_copper_to_bronze(
            extract_copper_snapshot(file_pattern, snapshot_date_str),
            resource_name,
            target,
        )
        emit_load_id(load_info)

    return main
