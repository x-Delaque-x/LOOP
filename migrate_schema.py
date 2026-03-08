"""
Schema Migration: Flat golden_events -> Normalized sources/venues/events

This script:
1. Creates the new tables (sources, venues, events)
2. Seeds sources from ri_sources.json
3. Seeds venues from the ADDRESS_MAP
4. Migrates existing golden_events rows into the new events table
5. Drops the old golden_events table

Usage: python migrate_schema.py
"""
import json
import logging
from pathlib import Path

from sqlalchemy import text
from database_manager import SessionLocal, Source, Venue, Event, init_db, engine, Base
from enrichment.update_addresses import ADDRESS_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate")

SCOUT_REGISTRY = Path(__file__).parent / "scout" / "ri_sources.json"

# Known LibCal calendar IDs (discovered by probing)
LIBCAL_CAL_IDS = {
    "Cranston Public Library": "15394",
    "Providence Public Library": "8194",
    "West Warwick Public Library": "18438",
    "East Providence Public Library": "20146",
    "North Providence Union Free Library": "18490",
}

# Map platform strings to adapter names
PLATFORM_TO_ADAPTER = {
    "whofi": "whofi",
    "libcal": "libcal",
    "recdesk": "recdesk",
    "wordpress events": "wordpress",
    "wordpress": "wordpress",
    "custom": "drupal",
    "custom (civicplus)": "drupal",
    "civicplus": "drupal",
    "revize calendar": "drupal",
    "unknown": "drupal",
}


def seed_sources(session):
    """Seed the sources table from ri_sources.json."""
    if not SCOUT_REGISTRY.exists():
        log.warning("No ri_sources.json found, skipping source seeding")
        return

    with open(SCOUT_REGISTRY, "r", encoding="utf-8") as f:
        sources = json.load(f)

    count = 0
    for src in sources:
        name = src["name"]
        # Skip if already exists
        existing = session.query(Source).filter_by(name=name).first()
        if existing:
            continue

        platform = src.get("platform", "Unknown")
        adapter_name = PLATFORM_TO_ADAPTER.get(platform.lower(), "drupal")

        events_url = src.get("events_url", "") or ""
        api_endpoint = src.get("api_endpoint", "") or ""

        # Clean garbage values
        if "Not found" in events_url or "None found" in events_url:
            events_url = ""
        if "Not found" in api_endpoint or "None found" in api_endpoint:
            api_endpoint = ""

        cal_id = LIBCAL_CAL_IDS.get(name, "")

        source = Source(
            name=name,
            type=src.get("type", ""),
            website=src.get("website", ""),
            platform=platform,
            events_url=events_url,
            api_endpoint=api_endpoint,
            cal_id=cal_id,
            adapter_name=adapter_name,
            is_active=src.get("has_events", False),
            notes=src.get("notes", ""),
        )
        session.add(source)
        count += 1

    session.commit()
    log.info(f"Seeded {count} sources")


def seed_venues(session):
    """Seed the venues table from ADDRESS_MAP, linking to sources."""
    count = 0
    for location_name, full_address in ADDRESS_MAP.items():
        existing = session.query(Venue).filter_by(name=location_name).first()
        if existing:
            continue

        # Parse address into components
        parts = [p.strip() for p in full_address.split(",")]
        street = parts[0] if len(parts) > 0 else ""
        city = parts[1] if len(parts) > 1 else ""
        state_zip = parts[2].strip() if len(parts) > 2 else "RI"
        state_parts = state_zip.split()
        state = state_parts[0] if state_parts else "RI"
        zip_code = state_parts[1] if len(state_parts) > 1 else ""

        # Link to matching source
        source = session.query(Source).filter_by(name=location_name).first()
        source_id = source.id if source else None

        venue = Venue(
            name=location_name,
            address=full_address,
            city=city,
            state=state,
            zip_code=zip_code,
            source_id=source_id,
        )
        session.add(venue)
        count += 1

    session.commit()
    log.info(f"Seeded {count} venues")


def migrate_events(session):
    """Migrate existing golden_events into the new events table."""
    # Check if the old table exists
    result = session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'golden_events')"
    ))
    if not result.scalar():
        log.info("No golden_events table found, nothing to migrate")
        return

    # Read old events
    old_events = session.execute(text(
        "SELECT title, event_date, event_time, description, tags, "
        "location_name, source_url FROM golden_events"
    )).fetchall()

    if not old_events:
        log.info("No events in golden_events to migrate")
        return

    count = 0
    for title, event_date, event_time, description, tags, location_name, source_url in old_events:
        # Find matching venue
        venue = session.query(Venue).filter_by(name=location_name).first() if location_name else None

        # Find matching source
        source = session.query(Source).filter_by(name=location_name).first() if location_name else None

        # Check for duplicate
        existing = session.query(Event).filter_by(
            title=title,
            event_date=event_date or "",
            venue_id=venue.id if venue else None
        ).first()
        if existing:
            continue

        event = Event(
            title=title,
            event_date=event_date or "",
            event_time=event_time or "",
            description=description or "",
            tags=tags or "",
            source_url=source_url or "",
            venue_id=venue.id if venue else None,
            source_id=source.id if source else None,
        )
        session.add(event)
        count += 1

    session.commit()
    log.info(f"Migrated {count} events")


def drop_old_table(session):
    """Drop the old golden_events table."""
    result = session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'golden_events')"
    ))
    if result.scalar():
        session.execute(text("DROP TABLE golden_events"))
        session.commit()
        log.info("Dropped old golden_events table")


def run():
    log.info("=" * 60)
    log.info("Schema Migration: golden_events -> sources/venues/events")
    log.info("=" * 60)

    # Create new tables
    init_db()
    log.info("Created new tables")

    session = SessionLocal()

    # Step 1: Seed sources from registry
    seed_sources(session)

    # Step 2: Seed venues from address map
    seed_venues(session)

    # Step 3: Migrate existing events
    migrate_events(session)

    # Step 4: Drop old table
    drop_old_table(session)

    # Step 5: Link sources to municipalities if that table exists
    has_munis = session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'municipalities')"
    )).scalar()
    if has_munis:
        from migrate_municipalities import link_sources_to_municipalities, update_municipality_statuses
        link_sources_to_municipalities(session)
        update_municipality_statuses(session)
        log.info("Linked new sources to municipalities")

    session.close()

    log.info("=" * 60)
    log.info("Migration complete!")
    log.info("=" * 60)


if __name__ == "__main__":
    run()
