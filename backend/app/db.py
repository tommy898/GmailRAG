import os

import psycopg


def get_database_url():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    return database_url


def get_connection():
    return psycopg.connect(get_database_url())


def fetch_database_time():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("select now();")
            return cursor.fetchone()[0]
