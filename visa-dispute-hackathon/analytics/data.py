"""Read-only DuckDB/MotherDuck queries for the public analytics experience."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_S3_DUCKDB_URI = re.compile(r"^s3://[a-z0-9][a-z0-9.-]*/[A-Za-z0-9._/-]+\.duckdb$")
DISPUTE_SUBCATEGORIES = ("CARGO NO RECONOCIDO", "COBRO INDEBIDO")
CARD_PRODUCT_TYPES = ("CREDIT CARD", "DEBIT CARD")


def connect_motherduck(
    *,
    token: str | None = None,
    database: str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Connect to MotherDuck without placing the token in a connection string."""

    resolved_token = token or os.getenv("MOTHERDUCK_TOKEN")
    if not resolved_token:
        raise RuntimeError("MOTHERDUCK_TOKEN is required for the analytics database.")
    os.environ["MOTHERDUCK_TOKEN"] = resolved_token
    resolved_database = database or os.getenv("MOTHERDUCK_DATABASE", "lakehouse")
    if not _IDENTIFIER.fullmatch(resolved_database):
        raise ValueError("MOTHERDUCK_DATABASE must be a plain SQL identifier.")
    return duckdb.connect(f"md:{resolved_database}")


def connect_duckdb_file(
    source: str,
    *,
    catalog: str = "lakehouse",
    aws_region: str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Attach a local or private-S3 DuckDB file read-only under a stable catalog name."""

    if not _IDENTIFIER.fullmatch(catalog):
        raise ValueError("catalog must be a plain SQL identifier")
    resolved = source.strip()
    if resolved.startswith("s3://"):
        if not _S3_DUCKDB_URI.fullmatch(resolved):
            raise ValueError("ANALYTICS_DUCKDB_URI must reference one S3 .duckdb object")
    else:
        path = Path(resolved).expanduser().resolve()
        if not path.is_file() or path.suffix != ".duckdb":
            raise ValueError("ANALYTICS_DUCKDB_URI must reference an existing .duckdb file")
        resolved = str(path)

    connection = duckdb.connect()
    if resolved.startswith("s3://"):
        connection.execute("INSTALL httpfs; LOAD httpfs")
        region = aws_region or os.getenv("AWS_REGION", "sa-east-1")
        if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region):
            raise ValueError("AWS_REGION is invalid")
        connection.execute(
            f"CREATE SECRET analytics_s3 (TYPE s3, PROVIDER credential_chain, "
            f"CHAIN 'env', REGION '{region}')"
        )
    # DuckDB does not parameterize ATTACH identifiers or paths. The identifier is allow-listed and
    # a local path is SQL-escaped; S3 URIs are constrained to the character allow-list above.
    escaped_source = resolved.replace("'", "''")
    connection.execute(f"ATTACH '{escaped_source}' AS \"{catalog}\" (READ_ONLY)")
    return connection


@dataclass(slots=True)
class AnalyticsRepository:
    """Customer-safe aggregate queries over the synthetic lakehouse."""

    connection: duckdb.DuckDBPyConnection
    catalog: str = "lakehouse"
    schema: str = "silver"

    def __post_init__(self) -> None:
        for value in (self.catalog, self.schema):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"Unsafe database identifier: {value!r}")

    def _table(self, name: str) -> str:
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError(f"Unsafe table identifier: {name!r}")
        return f'"{self.catalog}"."{self.schema}"."{name}"'

    def query(self, sql: str, parameters: list[Any] | None = None) -> pd.DataFrame:
        return self.connection.execute(sql, parameters or []).fetchdf()

    def available_tables(self) -> set[str]:
        rows = self.query(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_catalog = ? AND table_schema = ?
            """,
            [self.catalog, self.schema],
        )
        return set(rows["table_name"])

    def headline_metrics(self) -> dict[str, float | int | None]:
        complaints = self._table("complaints")
        products = self._table("products")
        row = self.query(
            f"""
            WITH all_complaints AS (
                SELECT * FROM {complaints}
            ),
            dispute_intake AS (
                SELECT *
                FROM all_complaints
                WHERE upper(trim(subcategory)) IN (?, ?)
            ),
            card_disputes AS (
                SELECT c.*
                FROM dispute_intake c
                JOIN {products} p ON p.product_id = c.affected_product_id
                WHERE upper(trim(p.product_type)) IN (?, ?)
            )
            SELECT
                (SELECT count(*) FROM all_complaints) AS complaints,
                (SELECT count(*) FROM dispute_intake) AS dispute_intake,
                count(*) AS card_disputes,
                count(*) FILTER (WHERE upper(trim(reception_channel)) = 'CALL CENTER')
                    AS call_center_cases,
                100.0 * avg(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breach_pct,
                100.0 * avg(CASE WHEN is_repeat_complainer THEN 1 ELSE 0 END)
                    AS repeat_complainer_pct,
                median(resolution_days) FILTER (WHERE resolution_days IS NOT NULL)
                    AS median_resolution_days,
                quantile_cont(resolution_days, 0.90) FILTER (WHERE resolution_days IS NOT NULL)
                    AS p90_resolution_days,
                100.0 * avg(CASE WHEN origin_interaction_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS origin_link_pct
            FROM card_disputes
            """,
            [*DISPUTE_SUBCATEGORIES, *CARD_PRODUCT_TYPES],
        ).iloc[0]
        return row.to_dict()

    def card_dispute_breakdown(self, dimension: str) -> pd.DataFrame:
        allowed = {
            "country": "coalesce(cu.country, 'MISSING')",
            "channel": "coalesce(c.reception_channel, 'MISSING')",
            "status": "coalesce(c.status, 'MISSING')",
            "subcategory": "coalesce(c.subcategory, 'MISSING')",
            "priority": "coalesce(c.priority, 'MISSING')",
        }
        expression = allowed.get(dimension)
        if expression is None:
            raise ValueError(f"Unsupported breakdown: {dimension}")
        return self.query(
            f"""
            SELECT {expression} AS category, count(*) AS cases
            FROM {self._table("complaints")} c
            JOIN {self._table("products")} p ON p.product_id = c.affected_product_id
            LEFT JOIN {self._table("customers")} cu ON cu.customer_id = c.customer_id
            WHERE upper(trim(c.subcategory)) IN (?, ?)
              AND upper(trim(p.product_type)) IN (?, ?)
            GROUP BY 1
            ORDER BY 2 DESC
            """,
            [*DISPUTE_SUBCATEGORIES, *CARD_PRODUCT_TYPES],
        )

    def card_dispute_country_experience(self) -> pd.DataFrame:
        """Compare actionable experience indicators across represented countries."""

        return self.query(
            f"""
            SELECT coalesce(cu.country, 'MISSING') AS country,
                   count(*) AS cases,
                   100.0 * avg(CASE WHEN upper(trim(c.reception_channel)) = 'CALL CENTER'
                                    THEN 1 ELSE 0 END) AS call_center_pct,
                   100.0 * avg(CASE WHEN c.sla_breached THEN 1 ELSE 0 END)
                       AS sla_breach_pct,
                   100.0 * avg(CASE WHEN c.is_repeat_complainer THEN 1 ELSE 0 END)
                       AS repeat_complainer_pct,
                   median(c.resolution_days) FILTER (WHERE c.resolution_days IS NOT NULL)
                       AS median_resolution_days,
                   quantile_cont(c.resolution_days, 0.90)
                       FILTER (WHERE c.resolution_days IS NOT NULL) AS p90_resolution_days
            FROM {self._table("complaints")} c
            JOIN {self._table("products")} p ON p.product_id = c.affected_product_id
            LEFT JOIN {self._table("customers")} cu ON cu.customer_id = c.customer_id
            WHERE upper(trim(c.subcategory)) IN (?, ?)
              AND upper(trim(p.product_type)) IN (?, ?)
            GROUP BY 1
            ORDER BY cases DESC
            """,
            [*DISPUTE_SUBCATEGORIES, *CARD_PRODUCT_TYPES],
        )

    def card_dispute_monthly_trend(self) -> pd.DataFrame:
        """Return volume and outcome trends for the card-dispute proxy."""

        return self.query(
            f"""
            SELECT date_trunc('month', c.creation_date)::DATE AS month,
                   count(*) AS cases,
                   100.0 * avg(CASE WHEN c.sla_breached THEN 1 ELSE 0 END)
                       AS sla_breach_pct,
                   median(c.resolution_days) FILTER (WHERE c.resolution_days IS NOT NULL)
                       AS median_resolution_days,
                   sum(coalesce(c.compensation_granted, 0)) AS compensation_granted
            FROM {self._table("complaints")} c
            JOIN {self._table("products")} p ON p.product_id = c.affected_product_id
            WHERE upper(trim(c.subcategory)) IN (?, ?)
              AND upper(trim(p.product_type)) IN (?, ?)
            GROUP BY 1
            ORDER BY 1
            """,
            [*DISPUTE_SUBCATEGORIES, *CARD_PRODUCT_TYPES],
        )

    def complaint_linkage_quality(self) -> pd.DataFrame:
        return self.query(
            f"""
            SELECT
                count(*) AS complaints,
                100.0 * avg(CASE WHEN customer_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS customer_link_pct,
                100.0 * avg(CASE WHEN affected_product_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS product_link_pct,
                100.0 * avg(CASE WHEN origin_interaction_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS interaction_link_pct,
                100.0 * avg(CASE WHEN assigned_agent_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS agent_link_pct,
                100.0 * avg(CASE WHEN resolution_days IS NOT NULL THEN 1 ELSE 0 END)
                    AS resolution_days_available_pct
            FROM {self._table("complaints")}
            """
        )

    def call_center_outcomes(self, dimension: str = "reason_category") -> pd.DataFrame:
        allowed = {
            "reason_category": "reason_category",
            "contact_reason": "contact_reason",
            "interaction_type": "interaction_type",
            "channel": "channel",
        }
        column = allowed.get(dimension)
        if column is None:
            raise ValueError(f"Unsupported call-center dimension: {dimension}")
        return self.query(
            f"""
            SELECT coalesce({column}, 'MISSING') AS category,
                   count(*) AS interactions,
                   avg(wait_time_seconds) AS mean_wait_seconds,
                   median(wait_time_seconds) AS median_wait_seconds,
                   quantile_cont(wait_time_seconds, 0.90) AS p90_wait_seconds,
                   avg(duration_seconds) AS mean_duration_seconds,
                   quantile_cont(duration_seconds, 0.90) AS p90_duration_seconds,
                   100.0 * avg(CASE WHEN was_resolved THEN 1 ELSE 0 END) AS fcr_proxy_pct,
                   100.0 * avg(CASE WHEN requires_followup THEN 1 ELSE 0 END)
                       AS followup_pct,
                   100.0 * avg(CASE WHEN was_escalated THEN 1 ELSE 0 END)
                       AS escalation_pct
            FROM {self._table("call_center_interactions")}
            GROUP BY 1
            ORDER BY interactions DESC
            """
        )

    def accent_alignment(self) -> pd.DataFrame:
        return self.query(
            f"""
            SELECT
                CASE
                    WHEN customer_detected_accent IS NULL OR agent_used_accent IS NULL
                        THEN 'MISSING'
                    WHEN upper(trim(customer_detected_accent)) = upper(trim(agent_used_accent))
                        THEN 'MATCH'
                    ELSE 'MISMATCH'
                END AS accent_alignment,
                count(*) AS interactions,
                avg(wait_time_seconds) AS mean_wait_seconds,
                avg(duration_seconds) AS mean_duration_seconds,
                100.0 * avg(CASE WHEN was_resolved THEN 1 ELSE 0 END) AS fcr_proxy_pct,
                100.0 * avg(CASE WHEN requires_followup THEN 1 ELSE 0 END)
                    AS followup_pct,
                100.0 * avg(CASE WHEN was_escalated THEN 1 ELSE 0 END)
                    AS escalation_pct
            FROM {self._table("call_center_interactions")}
            GROUP BY 1
            ORDER BY interactions DESC
            """
        )

    def transcript_coverage(self) -> pd.DataFrame:
        return self.query(
            f"""
            SELECT
                coalesce(reason_category, 'MISSING') AS reason_category,
                count(*) AS interactions,
                100.0 * avg(CASE WHEN has_transcript THEN 1 ELSE 0 END)
                    AS transcript_available_pct,
                100.0 * avg(CASE WHEN has_recording THEN 1 ELSE 0 END)
                    AS recording_available_pct,
                100.0 * avg(CASE WHEN was_resolved THEN 1 ELSE 0 END) AS fcr_proxy_pct
            FROM {self._table("call_center_interactions")}
            GROUP BY 1
            ORDER BY interactions DESC
            """
        )

    def agent_capacity(self) -> pd.DataFrame:
        return self.query(
            f"""
            SELECT coalesce(agent_type, 'MISSING') AS agent_type,
                   coalesce(experience_level, 'MISSING') AS experience_level,
                   coalesce(country_of_origin, 'MISSING') AS country,
                   count(*) AS agents,
                   avg(avg_csat) AS mean_agent_csat,
                   median(avg_csat) AS median_agent_csat,
                   sum(total_monthly_interactions) AS monthly_interactions,
                   avg(total_monthly_interactions) AS mean_monthly_interactions
            FROM {self._table("service_agents")}
            GROUP BY 1, 2, 3
            ORDER BY monthly_interactions DESC
            """
        )

    def interaction_cost_proxy(self) -> pd.DataFrame:
        """Estimate loaded labor cost from duration and transparent salary assumptions."""

        return self.query(
            f"""
            WITH agent_rates AS (
                SELECT agent_id,
                       CASE upper(trim(country_of_origin))
                           WHEN 'COLOMBIA' THEN 7200.0
                           WHEN 'MEXICO' THEN 7575.0
                           WHEN 'ARGENTINA' THEN 10200.0
                       END
                       * CASE upper(trim(experience_level))
                           WHEN 'JUNIOR' THEN 1.00
                           WHEN 'MID-SENIOR' THEN 1.45
                           WHEN 'SPECIALIST' THEN 1.50
                           WHEN 'SENIOR' THEN 1.62
                       END
                       * 1.42 / 12 / 132 / 60 AS loaded_cost_per_minute_usd
                FROM {self._table("service_agents")}
            )
            SELECT coalesce(i.reason_category, 'MISSING') AS reason_category,
                   count(*) AS interactions,
                   count(r.loaded_cost_per_minute_usd) AS priced_interactions,
                   avg(i.duration_seconds) / 60 AS mean_duration_minutes,
                   avg(i.duration_seconds / 60 * r.loaded_cost_per_minute_usd)
                       AS mean_labor_cost_usd,
                   quantile_cont(i.duration_seconds / 60 * r.loaded_cost_per_minute_usd, 0.90)
                       AS p90_labor_cost_usd,
                   sum(i.duration_seconds / 60 * r.loaded_cost_per_minute_usd)
                       AS total_labor_cost_proxy_usd
            FROM {self._table("call_center_interactions")} i
            LEFT JOIN agent_rates r ON r.agent_id = i.agent_id
            GROUP BY 1
            ORDER BY total_labor_cost_proxy_usd DESC NULLS LAST
            """
        )

    def product_transaction_mix(self) -> pd.DataFrame:
        return self.query(
            f"""
            SELECT coalesce(p.product_type, 'MISSING') AS product_type,
                   coalesce(t.transaction_type, 'MISSING') AS transaction_type,
                   count(*) AS transactions,
                   sum(t.amount_usd) AS amount_usd
            FROM {self._table("transactions")} t
            LEFT JOIN {self._table("products")} p ON p.product_id = t.product_id
            GROUP BY 1, 2
            ORDER BY transactions DESC
            """
        )

    def data_inventory(self) -> pd.DataFrame:
        return self.query(
            """
            SELECT table_name,
                   count(*) AS columns
            FROM information_schema.columns
            WHERE table_catalog = ? AND table_schema = ?
            GROUP BY table_name
            ORDER BY table_name
            """,
            [self.catalog, self.schema],
        )
