"""
Migration: Add parent_event_id column to events table for recurring event expansion.

Safe to run multiple times (uses IF NOT EXISTS).

Usage: py migrate_add_recurrence_columns.py
"""
import logging
from sqlalchemy import text
from database_manager import engine, SessionLocal
from enrichment.recurrence_expander import expand_recurring_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_recurrence")

ALTER_STATEMENTS = [
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS parent_event_id INTEGER REFERENCES events(id);",
]


def run():
    log.info("Adding parent_event_id column to events table...")

    with engine.connect() as conn:
        for stmt in ALTER_STATEMENTS:
            conn.execute(text(stmt))
            log.info("  Column: parent_event_id")
        conn.commit()

    log.info("Column added. Expanding recurring events...")

    session = SessionLocal()
    expand_recurring_events(session)
    session.close()

    log.info("Migration complete.")


if __name__ == "__main__":
    run()
