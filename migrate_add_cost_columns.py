"""
Migration: Add cost and registration columns to events table.

Adds 3 new columns for cost tracking and registration links.
Also backfills cost_cents=0 for events already tagged "Free" by Gemini.
Safe to run multiple times (uses IF NOT EXISTS).

Usage: py migrate_add_cost_columns.py
"""
import logging
from sqlalchemy import text
from database_manager import engine, SessionLocal, Event
from enrichment.cost_parser import cost_from_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_cost")

ALTER_STATEMENTS = [
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS cost_text VARCHAR;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS cost_cents INTEGER;",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS registration_url VARCHAR;",
]


def run():
    log.info("Adding cost/registration columns to events table...")

    with engine.connect() as conn:
        for stmt in ALTER_STATEMENTS:
            conn.execute(text(stmt))
            col_name = stmt.split("IF NOT EXISTS ")[1].split()[0]
            log.info(f"  Column: {col_name}")
        conn.commit()

    log.info("Columns added. Backfilling cost from existing 'Free' tags...")

    session = SessionLocal()
    events = session.query(Event).filter(
        Event.cost_cents.is_(None),
        Event.tags.isnot(None),
        Event.tags != "",
    ).all()

    backfilled = 0
    for event in events:
        cost_text, cost_cents = cost_from_tags(event.tags)
        if cost_text is not None:
            event.cost_text = cost_text
            event.cost_cents = cost_cents
            backfilled += 1

    session.commit()
    session.close()

    log.info(f"Backfilled {backfilled} events with cost info from tags.")
    log.info("Migration complete.")


if __name__ == "__main__":
    run()
