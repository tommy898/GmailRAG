import argparse
import os
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "gmailrag.sqlite3"

sys.path.insert(0, str(BACKEND_ROOT))

from app.db import get_connection
from app.ingestion import (
    ensure_gmail_account,
    ensure_profile,
    replace_chunks_and_embeddings_for_email,
    stable_demo_profile_id,
    upsert_email,
)


def read_sqlite_emails(sqlite_path: Path, limit: int | None) -> list[dict]:
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row

    query = """
        select
            message_id,
            thread_id,
            from_email,
            to_email,
            subject,
            date,
            snippet,
            body
        from emails
        order by rowid
    """

    params = ()

    if limit is not None:
        query += " limit ?"
        params = (limit,)

    with connection:
        rows = connection.execute(query, params).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def get_required_env(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required")

    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate local SQLite GmailRAG demo data into Supabase."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Path to local gmailrag.sqlite3.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of emails to migrate for a smaller test run.",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Insert emails and chunks without creating embeddings.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    profile_email = get_required_env("DEMO_PROFILE_EMAIL")
    gmail_address = os.environ.get("DEMO_GMAIL_ADDRESS", profile_email)
    profile_id = stable_demo_profile_id(profile_email)

    emails = read_sqlite_emails(args.sqlite_path, args.limit)

    print(f"SQLite emails loaded: {len(emails)}")
    print(f"Embeddings enabled: {not args.skip_embeddings}")

    total_chunks = 0

    with get_connection() as conn:
        ensure_profile(conn, profile_id, profile_email)
        gmail_account_id = ensure_gmail_account(conn, profile_id, gmail_address)

        for index, email in enumerate(emails, start=1):
            email_id = upsert_email(conn, gmail_account_id, email)
            total_chunks += replace_chunks_and_embeddings_for_email(
                conn,
                email_id,
                email,
                embed_chunks=not args.skip_embeddings,
            )

            if index % 50 == 0:
                conn.commit()
                print(f"Migrated {index}/{len(emails)} emails.")

        conn.commit()

    print("Migration complete.")
    print(f"Emails migrated: {len(emails)}")
    print(f"Chunks created: {total_chunks}")


if __name__ == "__main__":
    main()
