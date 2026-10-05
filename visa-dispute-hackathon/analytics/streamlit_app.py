"""Public Streamlit dashboard for synthetic LATAM service analytics."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from analytics.data import AnalyticsRepository, connect_motherduck  # noqa: E402

st.set_page_config(
    page_title="LATAM dispute service analytics",
    page_icon="📊",
    layout="wide",
)


def _secret(name: str, default: str | None = None) -> str | None:
    try:
        return st.secrets.get(name, default)
    except FileNotFoundError:
        return os.getenv(name, default)


@st.cache_resource(show_spinner="Connecting to the synthetic analytics database…")
def repository() -> AnalyticsRepository:
    token = _secret("MOTHERDUCK_TOKEN")
    database = _secret("MOTHERDUCK_DATABASE", "lakehouse")
    schema = _secret("MOTHERDUCK_SCHEMA", "silver")
    connection = connect_motherduck(token=token, database=database)
    return AnalyticsRepository(
        connection, catalog=database or "lakehouse", schema=schema or "silver"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_dashboard_data() -> dict[str, object]:
    repo = repository()
    return {
        "headlines": repo.headline_metrics(),
        "country": repo.card_dispute_breakdown("country"),
        "country_experience": repo.card_dispute_country_experience(),
        "trend": repo.card_dispute_monthly_trend(),
        "channel": repo.card_dispute_breakdown("channel"),
        "status": repo.card_dispute_breakdown("status"),
        "subcategory": repo.card_dispute_breakdown("subcategory"),
        "priority": repo.card_dispute_breakdown("priority"),
        "call_reason": repo.call_center_outcomes("reason_category"),
        "call_channel": repo.call_center_outcomes("channel"),
        "accent": repo.accent_alignment(),
        "transcript": repo.transcript_coverage(),
        "linkage": repo.complaint_linkage_quality(),
        "agents": repo.agent_capacity(),
        "costs": repo.interaction_cost_proxy(),
        "transactions": repo.product_transaction_mix(),
        "inventory": repo.data_inventory(),
    }


def pct(value: float | int | None) -> str:
    return "Unavailable" if pd.isna(value) else f"{float(value):.2f}%"


def number(value: float | int | None) -> str:
    return "Unavailable" if pd.isna(value) else f"{int(value):,}"


def metric_row(metrics: dict[str, object]) -> None:
    cols = st.columns(5)
    cols[0].metric("Dispute-intake signals", number(metrics["dispute_intake"]))
    cols[1].metric("Card-linked cases", number(metrics["card_disputes"]))
    cols[2].metric(
        "Call-center share", pct(100 * metrics["call_center_cases"] / metrics["card_disputes"])
    )
    cols[3].metric("SLA breached", pct(metrics["sla_breach_pct"]))
    cols[4].metric("Repeat complainants", pct(metrics["repeat_complainer_pct"]))


def bar(frame: pd.DataFrame, category: str, value: str, title: str) -> None:
    st.subheader(title)
    chart = frame[[category, value]].set_index(category)
    st.bar_chart(chart, horizontal=True)


st.title("LATAM dispute service analytics")
st.caption(
    "Public, aggregate analysis of the synthetic hackathon dataset. "
    "It is not customer data, national prevalence, or evidence of causal impact."
)

try:
    data = load_dashboard_data()
except Exception as exc:  # pragma: no cover - deployment diagnostic
    st.error("The analytics database is temporarily unavailable.")
    st.exception(exc)
    st.stop()

metric_row(data["headlines"])

overview, experience, reliability, sustainability, methods = st.tabs(
    ["Dispute intake", "Customer experience", "Reliability", "Sustainability", "Methods"]
)

with overview:
    st.markdown(
        "`Cargo no reconocido` and `Cobro indebido` are intake labels. They do not prove fraud, "
        "liability, a chargeback, or a Visa code. Product linkage narrows the analysis to cards."
    )
    left, right = st.columns(2)
    with left:
        bar(data["subcategory"], "category", "cases", "Card-linked intake labels")
        bar(data["country"], "category", "cases", "Country mix")
    with right:
        bar(data["channel"], "category", "cases", "Reception channel")
        bar(data["status"], "category", "cases", "Current case status")
    st.dataframe(data["priority"], width="stretch", hide_index=True)
    st.subheader("Experience baseline by country")
    st.dataframe(data["country_experience"], width="stretch", hide_index=True)
    st.subheader("Monthly baseline")
    monthly = data["trend"].set_index("month")
    st.line_chart(monthly[["cases", "sla_breach_pct"]])
    st.caption(
        "Two scales share this compact view: case count and SLA-breach percentage. "
        "Use the table below for exact values."
    )
    st.dataframe(data["trend"], width="stretch", hide_index=True)

with experience:
    st.markdown(
        "FCR is a proxy based on `was_resolved`. Production FCR must also verify that the same "
        "case did not generate another contact within a defined window."
    )
    call_reason = data["call_reason"]
    selected = st.selectbox("Interaction cohort", call_reason["category"].tolist())
    cohort = call_reason.loc[call_reason["category"] == selected].iloc[0]
    cols = st.columns(5)
    cols[0].metric("Interactions", number(cohort["interactions"]))
    cols[1].metric("Mean wait", f"{cohort['mean_wait_seconds']:.0f}s")
    cols[2].metric("Mean duration", f"{cohort['mean_duration_seconds'] / 60:.1f} min")
    cols[3].metric("FCR proxy", pct(cohort["fcr_proxy_pct"]))
    cols[4].metric("Follow-up", pct(cohort["followup_pct"]))
    st.dataframe(call_reason, width="stretch", hide_index=True)
    st.subheader("Accent alignment as an experience diagnostic")
    st.dataframe(data["accent"], width="stretch", hide_index=True)
    st.caption(
        "Accent is evaluated only as a service-quality signal. It must never determine identity, "
        "eligibility, liability, priority, or an adverse outcome."
    )

with reliability:
    linkage = data["linkage"].iloc[0]
    cols = st.columns(4)
    cols[0].metric("Customer linkage", pct(linkage["customer_link_pct"]))
    cols[1].metric("Product linkage", pct(linkage["product_link_pct"]))
    cols[2].metric("Origin-interaction linkage", pct(linkage["interaction_link_pct"]))
    cols[3].metric("Resolution-days available", pct(linkage["resolution_days_available_pct"]))
    st.warning(
        "The source has no dependable complaint-to-transaction key. A production workflow must "
        "create immutable interaction, case, and confirmed-transaction links."
    )
    st.subheader("Transcript and recording coverage")
    st.dataframe(data["transcript"], width="stretch", hide_index=True)
    st.markdown(
        "**Reliability priorities:** confirm the transaction before action; preserve the original "
        "customer statement; expose missing evidence; distinguish accepted, pending, completed, "
        "rejected and reconciled tool states; and abstain rather than force a Visa code."
    )

with sustainability:
    st.markdown(
        "Operational sustainability means using the right level of human expertise, reducing "
        "repeat work, and measuring quality before optimizing speed. The table below shows workload "
        "and CSAT by synthetic agent cohort; it does not estimate actual payroll."
    )
    st.dataframe(data["agents"], width="stretch", hide_index=True)
    st.subheader("Illustrative labor-cost proxy")
    st.dataframe(data["costs"], width="stretch", hide_index=True)
    st.caption(
        "USD planning proxy based on published LATAM salary ranges, experience multipliers, "
        "a 1.42 loaded-cost multiplier and observed interaction duration. It is not payroll data."
    )
    st.subheader("Where automation can reduce avoidable work")
    st.markdown(
        "1. Rank candidate transactions before asking the caller to repeat details.\n"
        "2. Resolve descriptor confusion without opening an unnecessary dispute.\n"
        "3. Create the case, interaction, transcript and transaction links together.\n"
        "4. Prefill evidence checklists while keeping policy decisions deterministic.\n"
        "5. Route ambiguity, denial and irreversible actions to a person with a concise summary."
    )

with methods:
    st.markdown(
        "The app runs read-only aggregate SQL against `lakehouse.silver` in MotherDuck through "
        "DuckDB. Queries are cached for one hour. No row-level customer, transcript, document, "
        "telephone, email, address, card number or free-text complaint data is rendered."
    )
    st.dataframe(data["inventory"], width="stretch", hide_index=True)
    st.subheader("Known data gaps")
    st.markdown(
        "- Satisfaction surveys and digital events are not present in the current silver schema.\n"
        "- Complaint-to-transaction and complaint-to-origin-interaction lineage is unavailable.\n"
        "- The dataset has no card-network field; treating cards as Visa is a product assumption.\n"
        "- Synthetic correlations are descriptive and cannot establish causality or national prevalence."
    )
