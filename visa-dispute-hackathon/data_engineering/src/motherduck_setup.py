import os

import click
import duckdb
from dotenv import load_dotenv


load_dotenv()
md_token = os.getenv("MOTHERDUCK_LAKEHOUSE_TOKEN")

CATALOGS = ["prod", "sqlmesh_state"]

with duckdb.connect(
    "md:",
    config={
        "motherduck_token" : os.getenv("MOTHERDUCK_LAKEHOUSE_TOKEN")
    },
    read_only=False
) as con:
    for catalog in CATALOGS:
        con.sql(f"CREATE DATABASE IF NOT EXISTS {catalog}")
    
    click.echo("Lakehouse schemas initialized successfully in MotherDuck.")