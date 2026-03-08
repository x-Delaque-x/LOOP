# LOOP Architecture Document

## Project Overview
**LOOP (Local Opportunities and Outdoor Play)** is a localized data aggregator that centralizes children's and family events across Rhode Island. It autonomously scouts municipal library and recreation calendars, extracts event data, categorizes it with AI, geo-enriches it, and serves it through a unified Streamlit dashboard.

## Tech Stack
- **Language:** Python 3.14
- **Database:** PostgreSQL 16 + PostGIS 3.4 (Docker container `loop-db`, port 5432)
- **Frontend:** Streamlit (Glass UI design with PostGIS spatial queries)
- **AI:** Google Gemini API (`gemini-2.5-flash` via `google-genai` SDK)
- **Geocoding:** Geopy (Nominatim/OpenStreetMap)
- **Web Scraping:** Requests + BeautifulSoup4
- **ORM:** SQLAlchemy 2.0 + GeoAlchemy2
- **Config:** python-dotenv (`.env` file)

## Directory Structure

```
LOOP/
  .env                     # Secrets: DB creds, Gemini API key (gitignored)
  .env.example             # Template for .env (committed)
  config.py                # Centralized constants and env loading
  database_manager.py      # SQLAlchemy models: Source, Venue, Event (+ GoldenEvent alias)
  app.py                   # Streamlit dashboard (PostGIS spatial queries, Glass UI)
  mass_harvest.py          # ETL orchestration (concurrent fetch + batch tagging)
  migrate_schema.py        # One-time migration: golden_events -> normalized schema

  scout/
    discover.py            # AI-powered source discovery (Gemini analyzes websites)
    ri_sources.json        # Discovered source registry (generated output)

  adapters/
    base_adapter.py        # Abstract base: fetch_events() -> List[Dict], source_name
    whofi_adapter.py       # WhoFi HTML scraper
    libcal_adapter.py      # LibCal AJAX API adapter (weekly fetching, 3-tier fallback)
    recdesk_adapter.py     # RecDesk Calendar API + HTML scraper
    wordpress_adapter.py   # WordPress MEC/TEC event plugins
    drupal_adapter.py      # Drupal Views, CivicPlus, generic HTML

  enrichment/
    gemini_tagger.py       # Gemini AI batch tagging (15 events/call)
    update_addresses.py    # location_name -> street address dictionary mapper
    geocoder.py            # Nominatim geocoding -> PostGIS POINT (venue-level)
```

## Database Schema (Normalized)

Three tables with foreign key relationships: **Source -> Venue -> Event**

**Table: `sources`** (calendar data sources)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-incrementing primary key |
| name | String (unique) | Organization name |
| type | String | "library" or "recreation" |
| website | String | Main website URL |
| platform | String | "LibCal", "RecDesk", "WhoFi", etc. |
| events_url | String | Events/calendar page URL |
| api_endpoint | String | API endpoint (if applicable) |
| cal_id | String | LibCal calendar ID |
| adapter_name | String | "libcal", "recdesk", "whofi", "wordpress", "drupal" |
| is_active | Boolean | Whether to include in harvest |
| notes | Text | Discovery notes |
| last_harvested | DateTime | Last successful harvest timestamp |

**Table: `venues`** (physical locations, geocoded once)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-incrementing primary key |
| name | String | Venue/organization name |
| address | String | Full street address |
| city | String | City |
| state | String | State (default: "RI") |
| zip_code | String | ZIP code |
| location | Geography(POINT, 4326) | PostGIS point for spatial queries |
| source_id | Integer (FK) | References sources.id |

**Table: `events`** (individual events)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-incrementing primary key |
| title | String | Event title |
| event_date | String | Date as text (flexible format) |
| event_time | String | Time as text |
| description | Text | Event description |
| tags | String | Comma-separated master tags from AI |
| source_url | String | Link to original event page |
| venue_id | Integer (FK) | References venues.id |
| source_id | Integer (FK) | References sources.id |
| created_at | DateTime | Record creation timestamp |
| updated_at | DateTime | Last update timestamp |

## The ETL Pipeline

```
[1. Scout]  ->  [2. Extract]  ->  [3. Transform]  ->  [4. Load]  ->  [5. Enrich]  ->  [6. Serve]
```

### 1. Scout (`py -m scout.discover`)
- Starts with a seed list of 34 RI library/recreation websites
- Fetches each site's HTML
- Sends HTML to Gemini to identify the calendar platform (WhoFi, LibCal, RecDesk, etc.)
- Outputs `scout/ri_sources.json` with platform, events_url, api_endpoint for each source

### 2. Extract (`mass_harvest.py` -> adapters, concurrent)
- Reads active sources from the `sources` DB table
- Runs all adapters concurrently via `ThreadPoolExecutor` (6 workers)
- **WhoFi Adapter:** Scrapes HTML event cards, extracts via CSS selectors
- **LibCal Adapter:** AJAX API (`/ajax/calendar/list/`) with weekly intervals (5 requests/site)
- **RecDesk Adapter:** Calendar JSON API + HTML scraping fallback
- **WordPress Adapter:** Modern Events Calendar (MEC) + The Events Calendar (TEC)
- **Drupal Adapter:** Drupal Views, CivicPlus calendars, generic HTML
- Each adapter returns `List[Dict]` with standard keys

### 3. Transform (Gemini AI batch tagging)
- Events batched in groups of 15 for a single Gemini API call
- Returns JSON array of comma-separated tag strings
- Tags from: Education, Outdoors, STEM, Arts, Active, Social, Music, Crafts
- Age-specific tags with rules: Baby (0-2), Preschool (3-5), Kids (6-12), Teens (13-17), All Ages
- Falls back to individual tagging on batch parse failures

### 4. Load (upsert to PostgreSQL)
- Upserts to `events` using natural key: `(title, event_date, venue_id)`
- Venues created on-the-fly via `get_or_create_venue()`
- Existing records updated, new records inserted

### 5. Enrich (venue-level geo-enrichment)
- **Address mapping:** `update_addresses.py` has a dictionary of 34 known RI locations -> street addresses
- **Geocoding:** `geocoder.py` geocodes each *venue* once (not each event), writes PostGIS POINT (1 req/sec rate limit)

### 6. Serve (`streamlit run app.py`)
- User enters ZIP code -> geocoded to lat/lon via Nominatim (cached)
- JOIN query: `events` -> `venues` to get coordinates
- PostGIS `ST_DWithin` filters events within selected radius (server-side)
- `ST_Distance` calculates exact distance in miles
- Category + age tag filtering via `st.pills` (multi-select) and Pandas `str.contains()` regex
- Renders: hero banner, metric cards, side-by-side map + scrollable event cards

## Source Coverage (as of March 2026)

### Confirmed Platforms (27 sources with events)
| Platform | Count | Examples |
|----------|-------|---------|
| RecDesk | 7 | NK Rec, Warwick, Cranston, Coventry, Barrington, Cumberland, Lincoln |
| LibCal | 7 | Cranston Library, Providence, Barrington, East Providence, Cumberland, N. Providence, West Warwick |
| WhoFi | 1 | North Kingstown Free Library |
| CivicPlus | 3 | SK Library, SK Rec, EG Rec |
| WordPress | 2 | Woonsocket Library, Tiverton Library |
| Custom/Drupal | 4 | EG Library, Coventry Library, Westerly Library, Rogers Free Library |
| Unknown | 3 | Warwick Library, Lincoln Library, Middletown Library (hijacked domain) |

### Unreachable (5 sources - wrong URLs or sites down)
Narragansett Library, Smithfield Library, Johnston Library, Newport Library, Exeter Library

## UI Design
- **Glass UI:** Custom CSS with rounded containers, subtle shadows, semi-transparent backgrounds
- **Sidebar:** ZIP code input, radius slider (1-50 miles), tag pills filter
- **Main area:** Dynamic map (st.map) + scrollable event cards
- **Event cards:** 3:1 column layout — title/date/tags/description on left, direction/source buttons on right
- **Master categories in `st.pills`:** Education, Outdoors, STEM, Arts, Active, Social, Music, Crafts

## Performance Optimizations
- **Concurrent fetching:** 6-worker ThreadPoolExecutor runs all adapters in parallel (~27s vs ~120s sequential)
- **Batch AI tagging:** 15 events per Gemini call (~9 calls vs ~130+ individual)
- **Weekly LibCal fetching:** 5 requests per site instead of 30 daily
- **Venue-level geocoding:** Geocode each venue once, reuse for all events at that location
- **Full harvest:** ~2-3 minutes (previously ~28 minutes)

## Key Design Patterns
- **Adapter pattern:** All scrapers inherit `BaseAdapter`, return uniform dicts
- **Normalized schema:** Source -> Venue -> Event with foreign keys (replaces flat golden_events)
- **DB-driven registry:** `mass_harvest.py` reads active sources from `sources` table
- **Single source of truth:** `config.py` for constants, `sources` table for registry
- **Graceful degradation:** App shows "Database Offline" instead of crashing when DB is down
- **PostGIS server-side filtering:** `ST_DWithin` instead of client-side distance calc
