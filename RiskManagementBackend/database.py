import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# Load the project-local .env file without overriding variables already set
# by the process environment.
load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)


def get_db_connection() -> psycopg.Connection:
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("DB_PASSWORD is not configured in the local .env file.")

    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "risk_management_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=password,
        row_factory=dict_row,
    )
