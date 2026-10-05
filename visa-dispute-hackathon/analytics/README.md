# Public LATAM service analytics

This Streamlit app publishes aggregate analysis from the synthetic MotherDuck lakehouse. It is designed to improve dispute intake, customer experience, operational reliability and sustainable use of human support.

## Run locally

From `visa-dispute-hackathon/`:

```bash
uv sync --extra analytics
uv run --extra analytics streamlit run analytics/streamlit_app.py
```

Set these values in the ignored `.env` or in the environment before starting:

```text
MOTHERDUCK_TOKEN=...
MOTHERDUCK_DATABASE=lakehouse
MOTHERDUCK_SCHEMA=silver
```

The app performs only read-only aggregate queries and never displays customer rows, transcripts, complaint descriptions, contact details, document numbers or card numbers.

## Streamlit Community Cloud

1. Connect the public GitHub repository to Streamlit Community Cloud.
2. Select `visa-dispute-hackathon/analytics/streamlit_app.py` as the entry point.
3. Add `MOTHERDUCK_TOKEN`, `MOTHERDUCK_DATABASE` and `MOTHERDUCK_SCHEMA` under **Advanced settings → Secrets**.
4. Deploy and copy the public app URL.

Do not commit the token or paste it into notebook output. The database share should remain read-only. Rotate the token if it is ever exposed.

## AWS BI alternative

Amazon QuickSight can query the private Aurora PostgreSQL database through a VPC connection, or query Parquet exported to S3 through Athena. It does not natively consume a DuckDB database file. Public anonymous dashboards require QuickSight Enterprise public sharing or capacity-based embedding, which is substantially more expensive than this hackathon needs. Streamlit Community Cloud is therefore the default public presentation layer; QuickSight remains a production BI option when governed access, scheduled refresh and organizational dashboards justify the cost.
