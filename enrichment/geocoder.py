"""
Geocoder - Enriches venues with lat/lon coordinates using Geopy Nominatim.
Writes PostGIS geography POINT values into the venue's location column.

Venues are geocoded once and their coordinates are reused for all events
at that venue — no need to geocode every event individually.
"""
import logging
import time

from geopy.geocoders import Nominatim
from sqlalchemy import text
from config import GEOCODER_USER_AGENT

log = logging.getLogger("enrichment.geocoder")

geolocator = Nominatim(user_agent=GEOCODER_USER_AGENT)


def geocode_venues(session):
    """
    For every venue where address IS NOT NULL but location IS NULL,
    geocode the address and update the location column with a PostGIS POINT.
    """
    result = session.execute(
        text("SELECT id, address, city, state, zip_code FROM venues WHERE address IS NOT NULL AND location IS NULL")
    )
    rows = result.fetchall()

    if not rows:
        log.info("  No venues to geocode.")
        return

    log.info(f"  Geocoding {len(rows)} venues...")
    geocoded = 0
    failed = 0

    for row_id, address, city, state, zip_code in rows:
        # Build full address string for geocoding
        full_address = address
        if city:
            full_address += f", {city}"
        if state:
            full_address += f", {state}"
        if zip_code:
            full_address += f" {zip_code}"
        try:
            location = geolocator.geocode(full_address)
            if location:
                session.execute(
                    text("""
                        UPDATE venues
                        SET location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                        WHERE id = :id
                    """),
                    {"lon": location.longitude, "lat": location.latitude, "id": row_id}
                )
                geocoded += 1
                log.debug(f"  Geocoded: {address} -> ({location.latitude}, {location.longitude})")
            else:
                failed += 1
                log.warning(f"  No result for: {full_address}")
        except Exception as e:
            failed += 1
            log.warning(f"  Geocoding error for '{full_address}': {e}")

        # Respect Nominatim rate limit: 1 request per second
        time.sleep(1)

    log.info(f"  Geocoded: {geocoded}, Failed: {failed}")
