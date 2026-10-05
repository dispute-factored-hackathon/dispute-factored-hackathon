import os

import click
import duckdb
from dotenv import load_dotenv

load_dotenv()
# Get the local lakehouse file path from environment variables
lakehouse_path = os.getenv("LAKEHOUSE_LOCAL_PATH")

# Using 'SCHEMAS' instead of 'CATALOGS' since a local DuckDB file acts as a single catalog
SCHEMAS = ["prod", "sqlmesh_state"]

# Connect to the local DuckDB file
with duckdb.connect(
    database=lakehouse_path,
    read_only=False
) as con:
    for schema in SCHEMAS:
        con.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    
    click.echo(f"Lakehouse schemas initialized successfully locally at {lakehouse_path}.")
