"""
Retag all events in Supabase with the current MASTER_TAGS / AUDIENCE_TAGS.

Uses SUPABASE_URL from .env so it connects directly to production instead
of the local Docker DB.  Commits every COMMIT_BATCH rows to avoid timeout.

Usage:
    py retag_supabase.py [--dry-run]
"""
import logging
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# ── load .env BEFORE importing anything that reads DATABASE_URL ──────────────
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_URL:
    sys.exit("ERROR: SUPABASE_URL not found in .env")

# Temporarily override DATABASE_URL so config.py / database_manager.py point
# at Supabase instead of the local Docker container.
os.environ["DATABASE_URL"] = SUPABASE_URL

from database_manager import Event  # noqa: E402 — must come after os.environ patch
from enrichment.gemini_tagger import tag_events_batch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("retag_supabase")

COMMIT_BATCH = 50   # rows per commit
DRY_RUN = "--dry-run" in sys.argv


def main():
    engine = create_engine(SUPABASE_URL, pool_pre_ping=True)

    with Session(engine) as session:
        events = session.query(Event).all()
        log.info(f"Fetched {len(events)} events from Supabase")

        if DRY_RUN:
            log.info("DRY RUN — no changes will be written")

        total_tagged = 0
        for i in range(0, len(events), COMMIT_BATCH):
            chunk = events[i:i + COMMIT_BATCH]

            # In dry-run mode: only tag the first chunk to verify quality, then stop
            if DRY_RUN and i > 0:
                log.info(f"  [DRY] Skipping remaining {len(events) - COMMIT_BATCH} events (sample verified)")
                break

            # Build dicts for the tagger
            event_dicts = [
                {"title": e.title, "description": e.description or ""}
                for e in chunk
            ]

            tag_strings = tag_events_batch(event_dicts)

            for ev, tags in zip(chunk, tag_strings):
                if not DRY_RUN:
                    ev.tags = tags

            if not DRY_RUN:
                session.commit()
                log.info(f"  Committed {i + len(chunk)}/{len(events)} events")
            else:
                for ev, tags in zip(chunk[:5], tag_strings[:5]):
                    log.info(f"  [DRY] '{ev.title[:50]}' → {tags}")

            total_tagged += len(chunk)

        log.info(f"Done — {total_tagged} events retagged" + (" (dry run)" if DRY_RUN else ""))


if __name__ == "__main__":
    main()
