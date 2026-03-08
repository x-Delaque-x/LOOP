# LOOP - Local Opportunities and Outdoor Play

A localized data aggregator that centralizes children's and family events across Rhode Island. LOOP autonomously scouts municipal library and recreation calendars, categorizes events using AI, and maps them geospatially through a unified Streamlit dashboard.

## How It Works

```
Scout (discover sources)  ->  Harvest (scrape + AI tag)  ->  Enrich (geocode)  ->  Serve (Streamlit)
```

1. **Scout** uses 39 RI municipalities as the organizing unit, then uses Gemini AI to identify each town's calendar platforms
2. **Harvest** runs platform-specific adapters concurrently (6 workers), then batch-tags with Gemini (15 events/call)
3. **Enrich** geocodes each venue once via Nominatim, reuses coordinates for all events at that location
4. **Serve** displays events on an interactive map with distance-based filtering via PostGIS

## Prerequisites

- Python 3.10+
- Docker Desktop
- Google Gemini API key ([Get one here](https://aistudio.google.com/apikey))

## Quick Start

```bash
# 1. Create and activate virtual environment
py -m venv .venv
source .venv/Scripts/activate  # Git Bash on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: add your GEMINI_API_KEY

# 4. Start database (Docker Desktop must be running)
docker compose up -d
py database_manager.py

# 5. Seed sources, venues, and municipalities
py migrate_schema.py
py migrate_municipalities.py

# 6. Run the full ETL pipeline (~2-3 minutes)
py mass_harvest.py

# 7. Launch the dashboard
streamlit run app.py
```

## Database Schema

Normalized design: **Municipality -> Source -> Venue -> Event**

- **municipalities** — all 39 RI municipalities with library/recreation scouting status
- **sources** — calendar data sources (platform, adapter config, active flag, linked to municipality)
- **venues** — physical locations with PostGIS POINT coordinates (geocoded once)
- **events** — individual events linked to venues and sources via foreign keys
- **url_submissions** — crowdsourced calendar URLs from users (pending admin review)

## Current Source Coverage

27 of 34 scouted sources are active, 12 currently producing events:

| Platform | Sources |
|----------|---------|
| **LibCal** (7) | Cranston, Providence, Barrington, East Providence, Cumberland, N. Providence, West Warwick libraries |
| **RecDesk** (7) | NK, Warwick, Cranston, Coventry, Barrington, Cumberland, Lincoln rec departments |
| **WhoFi** (1) | North Kingstown Free Library |
| **CivicPlus** (3) | SK Library, SK Rec, EG Rec |
| **WordPress** (2) | Woonsocket, Tiverton libraries |
| **Custom** (7) | Various Drupal/other library sites |

## Project Structure

```
config.py              - Centralized configuration (DB, API keys, master tags)
database_manager.py    - SQLAlchemy models: Municipality, Source, Venue, Event, URLSubmission
app.py                 - Streamlit dashboard with PostGIS spatial queries, coverage, Glass UI
mass_harvest.py        - Concurrent ETL pipeline (fetch, batch tag, upsert, geocode)
migrate_schema.py      - One-time migration: seeds sources/venues from registry
migrate_municipalities.py - Seeds 39 RI municipalities, links existing sources

scout/
  ri_municipalities.py - Registry of all 39 RI municipalities
  discover.py          - Municipality-driven source discovery (Gemini analyzes websites)
  ri_sources.json      - Discovered source registry (generated)

adapters/
  base_adapter.py      - Abstract base class for all adapters
  whofi_adapter.py     - WhoFi HTML scraper
  libcal_adapter.py    - LibCal AJAX API adapter (weekly fetching, 3-tier fallback)
  recdesk_adapter.py   - RecDesk Calendar API + HTML scraper
  wordpress_adapter.py - WordPress MEC/TEC event plugins
  drupal_adapter.py    - Drupal Views, CivicPlus, generic HTML

enrichment/
  gemini_tagger.py     - Gemini AI batch tagging (15 events/call)
  update_addresses.py  - Location name to street address mapper (34 RI venues)
  geocoder.py          - Geopy/Nominatim geocoding (venue-level)

tests/
  test_models.py       - Database model smoke tests
  test_adapters.py     - Adapter instantiation tests
  test_municipalities.py - Municipality registry validation
  test_pipeline.py     - Pipeline component import tests
```

## Tech Stack

- **Database:** PostgreSQL 16 + PostGIS 3.4 (Docker)
- **Frontend:** Streamlit (Glass UI with hero banner, metric cards, event cards)
- **AI:** Google Gemini API (`gemini-2.5-flash` via `google-genai` SDK)
- **Geocoding:** Geopy (Nominatim/OpenStreetMap)
- **Scraping:** Requests + BeautifulSoup4
- **ORM:** SQLAlchemy 2.0 + GeoAlchemy2
- **Testing:** pytest (27 smoke tests)
