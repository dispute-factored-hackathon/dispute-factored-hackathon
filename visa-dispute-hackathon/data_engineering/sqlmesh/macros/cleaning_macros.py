import sqlglot
from sqlglot import exp
from sqlmesh import macro
from sqlmesh.core.macros import MacroEvaluator


@macro()
def LATEST_LOAD(
    evaluator: MacroEvaluator,
    table_alias: exp.Expression,
    table_name: exp.Expression,
    partition_column: exp.Expression,
) -> exp.Expression:
    """Row filter: keep only rows of the most recent load for each partition value.

    Bronze is append-only, so a re-delivered photo adds a new load; the newest one wins.
    The contract acts as a gate outside SQLMesh (the job stops before silver if it fails).

    Usage: SELECT * FROM bronze.customers AS c WHERE @LATEST_LOAD(c, 'bronze.customers', snapshot_ts)
    """
    alias = table_alias.name
    table = table_name.name
    partition = partition_column.name

    # dlt load ids are epoch-like strings, so compare them numerically
    predicate = f"""
        {alias}._dlt_load_id::DOUBLE = (
            SELECT MAX(latest._dlt_load_id::DOUBLE)
            FROM {table} AS latest
            WHERE latest.{partition} = {alias}.{partition}
        )
    """
    return sqlglot.parse_one(predicate, dialect="duckdb")


@macro()
def NORMALIZE_STRING(evaluator: MacroEvaluator, column_name: exp.Expression) -> exp.Expression:
    """Normalize string by trimming, converting to uppercase, and stripping accents."""
    return exp.Anonymous(
        this="STRIP_ACCENTS", expressions=[exp.Trim(this=exp.Upper(this=column_name))]
    )


@macro()
def SAFE_CAST(
    evaluator: MacroEvaluator,
    column_name: exp.Expression,
    target_datatype: exp.Expression,
) -> exp.Expression:
    """Trim input column and safely cast to the target data type."""
    datatype_value = target_datatype.this if target_datatype.is_string else str(target_datatype)
    resolved_datatype = exp.DataType.build(datatype_value)

    return exp.TryCast(
        this=exp.Trim(this=column_name),
        to=resolved_datatype,
    )
