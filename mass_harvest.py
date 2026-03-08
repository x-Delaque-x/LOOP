"""
LOOP Mass Harvest -- Full ETL Pipeline
Reads sources from the database, runs the appropriate adapter for each,
tags events with Gemini AI (in batches), and geo-enriches venues.

Optimizations:
- Concurrent adapter execution via ThreadPoolExecutor
- Batch Gemini tagging (15 events per API call)
- LibCal weekly fetching (5 requests instead of 30)

Usage: python mass_harvest.py
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from database_manager import SessionLocal, init_db, Source, Venue, Event
from adapters.whofi_adapter import WhoFiAdapter
from adapters.libcal_adapter import LibCalAdapter
from adapters.recdesk_adapter import RecDeskAdapter
from adapters.wordpress_adapter import WordPressAdapter
from adapters.drupal_adapter import DrupalAdapter
from enrichment.gemini_tagger import tag_events_batch
from enrichment.geocoder import geocode_venues

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mass_harvest")

ADAPTER_MAP = {
    "whofi": WhoFiAdapter,
    "libcal": LibCalAdapter,
    "recdesk": RecDeskAdapter,
    "wordpress": WordPressAdapter,
    "drupal": DrupalAdapter,
}

MAX_WORKERS = 6  # concurrent adapter threads


def build_adapter(source: Source):
    """Instantiate the right adapter for a given source."""
    adapter_cls = ADAPTER_MAP.get(source.adapter_name, DrupalAdapter)

    kwargs = {
        "name": source.name,
        "website": source.website,
        "events_url": source.events_url or "",
    }

    if source.adapter_name == "whofi":
        kwargs["api_endpoint"] = source.api_endpoint or ""
    elif source.adapter_name == "libcal":
        kwargs["api_endpoint"] = source.api_endpoint or ""
        kwargs["cal_id"] = source.cal_id or ""

    return adapter_cls(**kwargs)


def get_or_create_venue(session, location_name: str, source: Source) -> Venue:
    """Get an existing venue by name, or create a stub for later enrichment."""
    venue = session.query(Venue).filter_by(name=location_name).first()
    if not venue:
        venue = Venue(
            name=location_name,
            source_id=source.id,
        )
        session.add(venue)
        session.flush()  # get the ID
    return venue


def upsert_event(session, event_dict: dict, venue: Venue, source: Source):
    """Insert or update an event based on (title, event_date, venue_id)."""
    existing = session.query(Event).filter_by(
        title=event_dict["title"],
        event_date=event_dict.get("event_date", ""),
        venue_id=venue.id,
    ).first()

    if existing:
        for key in ("event_time", "description", "tags", "source_url"):
            val = event_dict.get(key)
            if val:
                setattr(existing, key, val)
        existing.updated_at = datetime.utcnow()
    else:
        session.add(Event(
            title=event_dict["title"],
            event_date=event_dict.get("event_date", ""),
            event_time=event_dict.get("event_time", ""),
            description=event_dict.get("description", ""),
            tags=event_dict.get("tags", ""),
            source_url=event_dict.get("source_url", ""),
            venue_id=venue.id,
            source_id=source.id,
        ))


def fetch_source_events(source: Source):
    """Fetch events for a single source (runs in a thread)."""
    adapter = build_adapter(source)
    try:
        events = adapter.fetch_events()
        return source, events, None
    except Exception as e:
        return source, [], e


def run():
    """Execute the full ETL pipeline."""
    start_time = time.time()

    log.info("=" * 60)
    log.info("LOOP Mass Harvest - Starting Full ETL Pipeline")
    log.info("=" * 60)

    init_db()
    session = SessionLocal()

    # Load active sources from the database
    sources = session.query(Source).filter_by(is_active=True).all()
    if not sources:
        log.warning("No active sources in database. Run migrate_schema.py first.")
        session.close()
        return

    log.info(f"Loaded {len(sources)} active sources")

    # -------------------------------------------------------------------
    # Phase 1: Extract — fetch events concurrently from all sources
    # -------------------------------------------------------------------
    log.info(f"\n--- Phase 1: Fetching events ({MAX_WORKERS} concurrent workers) ---")
    fetch_start = time.time()
    source_events = {}  # source -> list of event dicts
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_source_events, src): src for src in sources}

        for future in as_completed(futures):
            source, events, error = future.result()
            if error:
                log.error(f"  {source.name}: FAILED - {error}")
                results.append((source.name, f"FAILED: {error}"))
            else:
                source_events[source.id] = (source, events)
                log.info(f"  {source.name}: {len(events)} events fetched")

    fetch_elapsed = time.time() - fetch_start
    total_fetched = sum(len(evts) for _, evts in source_events.values())
    log.info(f"  Fetch phase complete: {total_fetched} events in {fetch_elapsed:.1f}s")

    # -------------------------------------------------------------------
    # Phase 2: Transform — batch AI tagging
    # -------------------------------------------------------------------
    log.info("\n--- Phase 2: AI tagging (batch mode) ---")
    tag_start = time.time()

    # Collect all events into a flat list for batch tagging
    all_events_flat = []
    event_source_map = []  # parallel list: which source each event belongs to

    for source_id, (source, events) in source_events.items():
        for ev in events:
            all_events_flat.append(ev)
            event_source_map.append(source)

    if all_events_flat:
        tag_results = tag_events_batch(all_events_flat)

        # Apply tags back to event dicts
        for i, tags in enumerate(tag_results):
            all_events_flat[i]["tags"] = tags

    tag_elapsed = time.time() - tag_start
    log.info(f"  Tagged {len(all_events_flat)} events in {tag_elapsed:.1f}s")

    # -------------------------------------------------------------------
    # Phase 3: Load — upsert events into database
    # -------------------------------------------------------------------
    log.info("\n--- Phase 3: Upserting to database ---")
    load_start = time.time()
    total_events = 0

    for source_id, (source, events) in source_events.items():
        try:
            for event_dict in events:
                loc_name = event_dict.get("location_name", source.name)
                venue = get_or_create_venue(session, loc_name, source)
                upsert_event(session, event_dict, venue, source)

            session.commit()
            source.last_harvested = datetime.utcnow()
            session.commit()

            total_events += len(events)
            results.append((source.name, len(events)))

        except Exception as e:
            log.error(f"  {source.name}: DB upsert FAILED - {e}")
            session.rollback()
            results.append((source.name, f"FAILED: {e}"))

    load_elapsed = time.time() - load_start
    log.info(f"  Upserted {total_events} events in {load_elapsed:.1f}s")

    # -------------------------------------------------------------------
    # Phase 4: Geocode venues
    # -------------------------------------------------------------------
    log.info("\n--- Phase 4: Geocoding Venues ---")
    geocode_venues(session)
    session.commit()

    session.close()

    # Summary
    total_elapsed = time.time() - start_time
    log.info("\n" + "=" * 60)
    log.info(f"Mass harvest complete in {total_elapsed:.1f}s")
    log.info(f"  Fetch: {fetch_elapsed:.1f}s | Tag: {tag_elapsed:.1f}s | Load: {load_elapsed:.1f}s")
    log.info(f"  Total events: {total_events}")
    log.info("=" * 60)
    log.info("\nResults by source:")
    for name, count in results:
        status = f"{count} events" if isinstance(count, int) else count
        symbol = "+" if isinstance(count, int) and count > 0 else " "
        log.info(f"  {symbol} {name}: {status}")


if __name__ == "__main__":
    run()
