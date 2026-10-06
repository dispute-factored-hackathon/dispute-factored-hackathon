from __future__ import annotations

import duckdb
import pytest

from analytics.data import AnalyticsRepository, connect_duckdb_file


@pytest.fixture
def repository() -> AnalyticsRepository:
    connection = duckdb.connect()
    connection.execute("CREATE SCHEMA silver")
    connection.execute(
        """
        CREATE TABLE silver.customers(customer_id VARCHAR, country VARCHAR);
        INSERT INTO silver.customers VALUES ('C1', 'MEXICO'), ('C2', 'COLOMBIA');
        CREATE TABLE silver.products(
            product_id VARCHAR, customer_id VARCHAR, product_type VARCHAR
        );
        INSERT INTO silver.products VALUES
            ('P1', 'C1', 'CREDIT CARD'), ('P2', 'C2', 'DEBIT CARD');
        CREATE TABLE silver.complaints(
            complaint_id VARCHAR, customer_id VARCHAR, subcategory VARCHAR,
            affected_product_id VARCHAR, reception_channel VARCHAR, status VARCHAR,
            priority VARCHAR, sla_breached BOOLEAN, is_repeat_complainer BOOLEAN,
            resolution_days INTEGER, origin_interaction_id VARCHAR,
            assigned_agent_id VARCHAR, creation_date TIMESTAMP,
            compensation_granted DOUBLE
        );
        INSERT INTO silver.complaints VALUES
            ('K1', 'C1', 'CARGO NO RECONOCIDO', 'P1', 'CALL CENTER', 'OPEN', 'HIGH',
             true, false, NULL, NULL, 'A1', '2025-01-10', 0),
            ('K2', 'C2', 'COBRO INDEBIDO', 'P2', 'APP', 'RESOLVED', 'MEDIUM',
             false, true, 10, 'I2', 'A2', '2025-02-10', 25),
            ('K3', 'C1', 'OTHER', 'P1', 'EMAIL', 'OPEN', 'LOW', false, false,
             NULL, NULL, NULL, '2025-03-10', 0);
        CREATE TABLE silver.call_center_interactions(
            interaction_id VARCHAR, agent_id VARCHAR, reason_category VARCHAR, contact_reason VARCHAR,
            interaction_type VARCHAR, channel VARCHAR, wait_time_seconds INTEGER,
            duration_seconds INTEGER, was_resolved BOOLEAN, requires_followup BOOLEAN,
            was_escalated BOOLEAN, customer_detected_accent VARCHAR,
            agent_used_accent VARCHAR, has_transcript BOOLEAN, has_recording BOOLEAN
        );
        INSERT INTO silver.call_center_interactions VALUES
            ('I1', 'A1', 'COMPLAINT', 'QUEJA', 'INBOUND CALL', 'PHONE', 60, 300,
             false, true, true, 'MEXICAN', 'MEXICAN', true, true),
            ('I2', 'A2', 'COMPLAINT', 'QUEJA', 'INBOUND CALL', 'PHONE', 120, 600,
             true, false, false, 'COLOMBIAN', 'MEXICAN', false, true);
        CREATE TABLE silver.service_agents(
            agent_id VARCHAR, agent_type VARCHAR, experience_level VARCHAR, country_of_origin VARCHAR,
            avg_csat DOUBLE, total_monthly_interactions INTEGER
        );
        INSERT INTO silver.service_agents VALUES
            ('A1', 'PHONE', 'JUNIOR', 'MEXICO', 4.2, 100),
            ('A2', 'PHONE', 'SENIOR', 'COLOMBIA', 4.4, 120);
        CREATE TABLE silver.transactions(
            product_id VARCHAR, transaction_type VARCHAR, amount_usd DOUBLE
        );
        INSERT INTO silver.transactions VALUES ('P1', 'PURCHASE', 25), ('P2', 'PURCHASE', 50);
        """
    )
    return AnalyticsRepository(connection, catalog="memory", schema="silver")


def test_headline_metrics_scope_to_card_dispute_intake(repository: AnalyticsRepository) -> None:
    metrics = repository.headline_metrics()

    assert metrics["complaints"] == 3
    assert metrics["dispute_intake"] == 2
    assert metrics["card_disputes"] == 2
    assert metrics["call_center_cases"] == 1
    assert metrics["sla_breach_pct"] == 50
    assert metrics["origin_link_pct"] == 50


def test_breakdown_rejects_untrusted_identifier(repository: AnalyticsRepository) -> None:
    with pytest.raises(ValueError, match="Unsupported breakdown"):
        repository.card_dispute_breakdown("country; DROP TABLE complaints")


def test_country_experience_preserves_comparable_baselines(
    repository: AnalyticsRepository,
) -> None:
    result = repository.card_dispute_country_experience().set_index("country")

    assert result.loc["MEXICO", "cases"] == 1
    assert result.loc["MEXICO", "call_center_pct"] == 100
    assert result.loc["COLOMBIA", "median_resolution_days"] == 10


def test_monthly_trend_tracks_volume_sla_and_compensation(
    repository: AnalyticsRepository,
) -> None:
    result = repository.card_dispute_monthly_trend()

    assert result["cases"].tolist() == [1, 1]
    assert result["sla_breach_pct"].tolist() == [100, 0]
    assert result["compensation_granted"].sum() == 25


def test_call_center_outcomes_preserve_operational_rates(repository: AnalyticsRepository) -> None:
    result = repository.call_center_outcomes().iloc[0]

    assert result["interactions"] == 2
    assert result["fcr_proxy_pct"] == 50
    assert result["followup_pct"] == 50
    assert result["escalation_pct"] == 50


def test_accent_alignment_is_diagnostic_not_identity(repository: AnalyticsRepository) -> None:
    result = repository.accent_alignment().set_index("accent_alignment")

    assert result.loc["MATCH", "interactions"] == 1
    assert result.loc["MISMATCH", "interactions"] == 1


def test_interaction_cost_proxy_uses_observed_duration(repository: AnalyticsRepository) -> None:
    result = repository.interaction_cost_proxy().iloc[0]

    assert result["priced_interactions"] == 2
    assert result["mean_duration_minutes"] == pytest.approx(7.5)
    assert result["mean_labor_cost_usd"] > 0


def test_local_duckdb_file_is_attached_read_only_with_stable_catalog(tmp_path) -> None:
    database_path = tmp_path / "treated lakehouse.duckdb"
    writer = duckdb.connect(str(database_path))
    writer.execute("CREATE SCHEMA silver; CREATE TABLE silver.customers(id INTEGER)")
    writer.execute("INSERT INTO silver.customers VALUES (1)")
    writer.close()

    connection = connect_duckdb_file(str(database_path), catalog="lakehouse")

    assert connection.execute("SELECT count(*) FROM lakehouse.silver.customers").fetchone() == (1,)
    with pytest.raises(duckdb.Error):
        connection.execute("INSERT INTO lakehouse.silver.customers VALUES (2)")


def test_duckdb_source_rejects_unsafe_catalog_and_non_database_file(tmp_path) -> None:
    text_file = tmp_path / "not-a-database.txt"
    text_file.write_text("synthetic")

    with pytest.raises(ValueError, match="catalog"):
        connect_duckdb_file(str(text_file), catalog='lakehouse"; DROP SCHEMA silver')
    with pytest.raises(ValueError, match=r"existing \.duckdb"):
        connect_duckdb_file(str(text_file))
