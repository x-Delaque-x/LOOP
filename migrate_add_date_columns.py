"""
Migration: Add date/time normalization columns to events table.

Adds 6 new columns for parsed dates, times, and recurring event tracking.
Safe to run multiple times (uses IF NOT EXISTS).

Usage: py migrate_add_date_columns.py
"""
import logging
from sqlalchemy import text
from database_manager import engine, SessionLocal
from enrichment.date_normalizer import normalize_dates

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_dates")

ALTER_STATEMENTS = [
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_date_start DATE;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_date_end DATE;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_time_start TIME;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_time_end TIME;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS recurrence_pattern VARCHAR;",
]


def run():
    log.info("Adding date normalization columns to events table...")

    with engine.connect() as conn:
        for stmt in ALTER_STATEMENTS:
            conn.execute(text(stmt))
            col_name = stmt.split("IF NOT EXISTS ")[1].split()[0]
            log.info(f"  Column: {col_name}")
        conn.commit()

    log.info("Columns added. Running date normalizer on existing events...")

    session = SessionLocal()
    normalize_dates(session)
    session.close()

    log.info("Migration complete.")


if __name__ == "__main__":
    run()
