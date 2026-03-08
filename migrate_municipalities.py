"""
Municipality Migration: Seeds the municipalities table and links existing sources.

This script:
1. Creates municipalities and url_submissions tables
2. Adds municipality_id column to existing sources table (ALTER TABLE)
3. Seeds all 39 RI municipalities from the registry
4. Links existing sources to their municipalities by name matching

Usage: python migrate_municipalities.py
"""
import logging
from sqlalchemy import text
from database_manager import SessionLocal, Source, init_db, engine, Base
from database_manager import Municipality

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_municipalities")


# Explicit overrides for sources whose names don't start with the municipality name
SOURCE_TO_MUNICIPALITY = {
    "Bristol (Rogers Free Library)": "Bristol",
    "Woonsocket Harris Public Library": "Woonsocket",
}


def add_municipality_column(session):
    """Add municipality_id FK to the sources table if it doesn't exist."""
    result = session.execute(text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.columns "
        "  WHERE table_name = 'sources' AND column_name = 'municipality_id'"
        ")"
    ))
    if result.scalar():
        log.info("municipality_id column already exists on sources")
        return

    session.execute(text(
        "ALTER TABLE sources ADD COLUMN municipality_id INTEGER REFERENCES municipalities(id)"
    ))
    session.commit()
    log.info("Added municipality_id column to sources table")


def seed_municipalities(session):
    """Seed all 39 RI municipalities."""
    from scout.ri_municipalities import RI_MUNICIPALITIES

    count = 0
    for muni in RI_MUNICIPALITIES:
        existing = session.query(Municipality).filter_by(name=muni["name"]).first()
        if existing:
            continue

        session.add(Municipality(
            name=muni["name"],
            county=muni["county"],
            population=muni["population"],
            has_library=muni["has_library"],
            has_recreation=muni["has_recreation"],
        ))
        count += 1

    session.commit()
    log.info(f"Seeded {count} municipalities")


def link_sources_to_municipalities(session):
    """Link existing sources to their municipalities by name matching."""
    municipalities = {m.name: m for m in session.query(Municipality).all()}
    sources = session.query(Source).filter(Source.municipality_id.is_(None)).all()

    linked = 0
    unlinked = []

    for source in sources:
        # Check explicit overrides first
        muni_name = SOURCE_TO_MUNICIPALITY.get(source.name)

        # Otherwise, find municipality whose name is a prefix of the source name
        if not muni_name:
            for name in sorted(municipalities.keys(), key=len, reverse=True):
                if source.name.lower().startswith(name.lower()):
                    muni_name = name
                    break

        if muni_name and muni_name in municipalities:
            source.municipality_id = municipalities[muni_name].id
            linked += 1
        else:
            unlinked.append(source.name)

    session.commit()
    log.info(f"Linked {linked} sources to municipalities")
    if unlinked:
        log.warning(f"Could not link {len(unlinked)} sources: {unlinked}")


def update_municipality_statuses(session):
    """Set library_status and recreation_status based on linked sources."""
    municipalities = session.query(Municipality).all()

    for muni in municipalities:
        sources = session.query(Source).filter_by(municipality_id=muni.id).all()

        lib_sources = [s for s in sources if s.type == "library"]
        rec_sources = [s for s in sources if s.type == "recreation"]

        if lib_sources:
            active_libs = [s for s in lib_sources if s.is_active]
            muni.library_status = "active" if active_libs else "scouted"
        # Leave as not_scouted if no library sources found

        if rec_sources:
            active_recs = [s for s in rec_sources if s.is_active]
            muni.recreation_status = "active" if active_recs else "scouted"

    session.commit()
    log.info("Updated municipality statuses")


def run():
    log.info("=" * 60)
    log.info("Municipality Migration")
    log.info("=" * 60)

    # Create new tables (municipalities, url_submissions)
    init_db()
    log.info("Created new tables")

    session = SessionLocal()

    # Step 1: Add FK column to sources
    add_municipality_column(session)

    # Step 2: Seed municipalities
    seed_municipalities(session)

    # Step 3: Link existing sources
    link_sources_to_municipalities(session)

    # Step 4: Update statuses
    update_municipality_statuses(session)

    # Summary
    muni_count = session.query(Municipality).count()
    linked_count = session.query(Source).filter(Source.municipality_id.isnot(None)).count()
    total_sources = session.query(Source).count()
    log.info(f"\nSummary: {muni_count} municipalities, {linked_count}/{total_sources} sources linked")

    session.close()
    log.info("=" * 60)
    log.info("Municipality migration complete!")
    log.info("=" * 60)


if __name__ == "__main__":
    run()
