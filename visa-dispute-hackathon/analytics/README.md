# Public LATAM service analytics

This Streamlit app publishes aggregate analysis from the synthetic MotherDuck lakehouse. It is designed to improve dispute intake, customer experience, operational reliability and sustainable use of human support.

## Run locally

From `visa-dispute-hackathon/`:

```bash
uv sync --extra analytics
uv run --extra analytics streamlit run analytics/streamlit_app.py
```

The preferred source is the private, versioned DuckDB file in AWS S3. Set these values in the
ignored `.env` or in Streamlit's encrypted secrets:

```text
ANALYTICS_DUCKDB_URI=s3://dispute-factored-duckdb-832271495954-sa-east-1/duckdb/lakehouse_v1.0.1.duckdb
ANALYTICS_DUCKDB_CATALOG=lakehouse
ANALYTICS_DUCKDB_SCHEMA=silver
AWS_REGION=sa-east-1
AWS_ACCESS_KEY_ID=...              # read-only GetObject credential
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...              # only when the credential is temporary
```

For local analysis, `ANALYTICS_DUCKDB_URI` may instead be an existing `.duckdb` file. MotherDuck
remains a compatibility fallback when `ANALYTICS_DUCKDB_URI` is absent:

```text
MOTHERDUCK_TOKEN=...
MOTHERDUCK_DATABASE=lakehouse
MOTHERDUCK_SCHEMA=silver
```

The app performs only read-only aggregate queries and never displays customer rows, transcripts, complaint descriptions, contact details, document numbers or card numbers.

## Streamlit Community Cloud

1. Connect the public GitHub repository to Streamlit Community Cloud.
2. Select `visa-dispute-hackathon/analytics/streamlit_app.py` as the entry point.
3. Under **Advanced settings → Secrets**, configure either the private-S3 values above or the
   MotherDuck fallback values.
4. Deploy and copy the public app URL.

Do not commit credentials or paste them into notebook output. S3 access must be limited to
`s3:GetObject` for the single database object (plus only the bucket-list permission needed to
resolve it). The DuckDB file is attached read-only and the bucket must remain private. Rotate any
credential if it is exposed.

## AWS BI alternative

Amazon QuickSight can query the private Aurora PostgreSQL database through a VPC connection, or query Parquet exported to S3 through Athena. It does not natively consume a DuckDB database file. Public anonymous dashboards require QuickSight Enterprise public sharing or capacity-based embedding, which is substantially more expensive than this hackathon needs. Streamlit Community Cloud is therefore the default public presentation layer; QuickSight remains a production BI option when governed access, scheduled refresh and organizational dashboards justify the cost.
