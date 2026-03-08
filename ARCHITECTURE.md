# LOOP Architecture Document

## Project Overview
**LOOP (Local Outings & Opportunities Platform)** is a localized event aggregator that centralizes events of all types across Rhode Island. It autonomously scouts municipal library and recreation calendars, extracts event data, categorizes it with AI, geo-enriches it, and serves it through a unified Streamlit dashboard.

## Tech Stack
- **Language:** Python 3.14
- **Database:** PostgreSQL 16 + PostGIS 3.4
  - **Local (ETL):** Docker container `loop-db`, port 5432
  - **Production:** Supabase (free tier), region `us-west-2`, session pooler connection
- **Frontend:** Streamlit (light theme, deployed on Streamlit Community Cloud)
- **AI:** Google Gemini API (`gemini-2.5-flash` via `google-genai` SDK)
- **Geocoding:** Geopy (Nominatim/OpenStreetMap)
- **Web Scraping:** Requests + BeautifulSoup4, Playwright (for JS-rendered pages like RecDesk)
- **ORM:** SQLAlchemy 2.0 + GeoAlchemy2 (`pool_pre_ping=True` for connection resilience)
- **Config:** python-dotenv (`.env` local) + `st.secrets` (Streamlit Cloud) via `_get_secret()` helper
- **Deployment:** Streamlit Community Cloud (auto-deploy from GitHub `main` branch)

## Directory Structure

```
LOOP/
  .env                     # Secrets: DB creds, Gemini API key (gitignored)
  .env.example             # Template for .env (committed)
  .streamlit/config.toml   # Forces light theme for Streamlit Cloud
  config.py                # Centralized constants and env loading (_get_secret for local/.env + cloud/st.secrets)
  database_manager.py      # SQLAlchemy models: Municipality, Source, Venue, Event, URLSubmission, Feedback
  app.py                   # Streamlit dashboard (PostGIS spatial queries, Glass UI, coverage)
  mass_harvest.py          # ETL orchestration (concurrent fetch + batch tagging)
  migrate_schema.py        # One-time migration: golden_events -> normalized schema
  migrate_municipalities.py # Seeds 39 RI municipalities, links sources

  scout/
    ri_municipalities.py   # Registry of all 39 RI municipalities
    discover.py            # Municipality-driven source discovery (Gemini analyzes websites)
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
    date_normalizer.py     # Freeform date text -> Date/Time columns (14+ format cascade)
    cost_parser.py         # Cost text -> (cost_text, cost_cents) normalization
    recurrence_expander.py # "Every Saturday" -> 4 concrete child events
    update_addresses.py    # location_name -> street address dictionary mapper
    geocoder.py            # Nominatim geocoding -> PostGIS POINT (venue-level)

  tests/
    test_models.py         # Model imports, columns, relationships, backward-compat alias
    test_adapters.py       # Adapter instantiation, BaseAdapter abstract check
    test_municipalities.py # Registry: 39 towns, valid counties, no dupes, sorted
    test_pipeline.py       # Config/enrichment imports, adapter map, cost parser
```

## Database Schema (Normalized)

Four core tables with foreign key relationships: **Municipality -> Source -> Venue -> Event**

**Table: `municipalities`** (all 39 RI municipalities)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-incrementing primary key |
| name | String (unique) | Municipality name |
| county | String | RI county (Bristol, Kent, Newport, Providence, Washington) |
| population | Integer | Census population |
| has_library | Boolean | Whether the town has a public library |
| has_recreation | Boolean | Whether the town has a rec department |
| library_status | String | not_scouted, scouted, active, no_events, unreachable |
| recreation_status | String | not_scouted, scouted, active, no_events, unreachable |

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
| municipality_id | Integer (FK) | References municipalities.id |

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
| event_date_start | Date | Parsed date for sort/filter |
| event_date_end | Date | Multi-day events |
| event_time_start | Time | Parsed start time |
| event_time_end | Time | Parsed end time |
| is_recurring | Boolean | Flags "Every Saturday" type events |
| recurrence_pattern | String | Raw recurrence pattern text |
| cost_text | String | Display: "Free", "$5/child", "Varies" |
| cost_cents | Integer | Queryable: 0=free, 500=$5, NULL=unknown |
| registration_url | String | Direct signup link |
| parent_event_id | Integer (FK) | References events.id (expanded recurring child) |
| created_at | DateTime | Record creation timestamp |
| updated_at | DateTime | Last update timestamp |

**Table: `url_submissions`** (crowdsourced URL submissions)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-incrementing primary key |
| municipality_id | Integer (FK) | References municipalities.id |
| url | String | Submitted calendar/events URL |
| source_type | String | "library" or "recreation" |
| submitter_note | Text | Optional note from submitter |
| status | String | pending, approved, rejected |
| created_at | DateTime | Submission timestamp |

**Table: `feedback`** (user feedback from dashboard)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-incrementing primary key |
| name | String | Submitter name (optional) |
| feedback | Text | Feedback content |
| created_at | DateTime | Submission timestamp |

## The ETL Pipeline

```
[1. Scout] -> [2. Extract] -> [3. Transform] -> [4. Load] -> [5. Normalize] -> [6. Expand] -> [7. Cleanup] -> [8. Geocode] -> [9. Serve]
```

### 1. Scout (`py -m scout.discover`)
- Municipality-driven: reads all 39 RI municipalities from the database
- For each unscouted municipality, finds library and recreation department URLs
- **URL resolution** (`find_source_url()`): DB source first -> `KNOWN_SEEDS` fallback -> URL pattern guessing
- Fetches each site's HTML, sends to Gemini to identify the calendar platform
- Creates Source records linked to the municipality, updates status (active/scouted/unreachable)
- Exports results to `scout/ri_sources.json` for backward compatibility
- Flags: `--rescan` to re-scout all, `--town "Name"` to scout a specific town

### 2. Extract (`mass_harvest.py` -> adapters, concurrent)
- Reads active sources from the `sources` DB table
- Runs all adapters concurrently via `ThreadPoolExecutor` (6 workers)
- **WhoFi Adapter:** Scrapes HTML event cards, extracts via CSS selectors
- **LibCal Adapter:** AJAX API (`/ajax/calendar/list/`) with weekly intervals (5 requests/site)
- **RecDesk Adapter:** Calendar JSON API + HTML scraping fallback
- **WordPress Adapter:** Modern Events Calendar (MEC) + The Events Calendar (TEC)
- **Drupal Adapter:** Drupal Views, CivicPlus calendars, generic HTML
- Each adapter returns `List[Dict]` with standard keys + optional `cost_text`, `registration_url`

### 3. Transform (Gemini AI batch tagging)
- Events batched in groups of 15 for a single Gemini API call
- Returns JSON array of comma-separated tag strings
- Tags from: Arts, Music, Food & Drink, Outdoors, Sports & Fitness, Education, STEM, Community, Nightlife, Family
- Audience tags: Family, Kids (0-12), Teens (13-17), Adults (18+), Seniors (65+), All Ages
- Falls back to individual tagging on batch parse failures

### 4. Load (upsert to PostgreSQL)
- Upserts to `events` using natural key: `(title, event_date, venue_id)`
- Venues created on-the-fly via `get_or_create_venue()`
- Existing records updated, new records inserted
- Cost parsing: adapter `cost_text` -> `parse_cost()` -> `cost_cents`; fallback infers from "Free" tag

### 5. Normalize (date/time parsing)
- `date_normalizer.py` parses freeform `event_date` text -> `event_date_start` (Date)
- 14+ format cascade: ISO, US long/short, day-prefixed, ordinal, embedded time
- Detects recurring patterns ("Every Saturday") -> sets `is_recurring=True`
- Never modifies `event_date` text (upsert key depends on it)

### 6. Expand recurring events
- `recurrence_expander.py` generates concrete child events for next 4 weeks
- "Every Saturday" -> 4 event rows with specific `event_date_start`, linked via `parent_event_id`
- Idempotent: checks existing children; cleans up past expansions

### 7. Cleanup stale events
- `cleanup_stale_events()` in `mass_harvest.py` deletes events whose `event_date_start` is before yesterday
- Skips recurring parents (`is_recurring=True`) — they generate future children
- Skips events with NULL `event_date_start` — can't determine if stale
- UI query also filters out past events and expanded children (`parent_event_id IS NULL`) at query time

### 8. Geocode (venue-level geo-enrichment)
- **Address mapping:** `update_addresses.py` has a dictionary of 34 known RI locations -> street addresses
- **Geocoding:** `geocoder.py` geocodes each *venue* once (not each event), writes PostGIS POINT (1 req/sec rate limit)

### 9. Serve (`streamlit run app.py`)
- User enters ZIP code -> geocoded to lat/lon via Nominatim (cached)
- JOIN query: `events` -> `venues` to get coordinates + cost/registration/date fields
- PostGIS `ST_DWithin` filters events within selected radius (server-side)
- `ST_Distance` calculates exact distance in miles
- **Sidebar controls:** ZIP, radius, category pills, audience pills, sort (Closest/Soonest), date filter (Today/This Weekend/Next 7/30 Days), cost filter (All/Free Only/Paid OK)
- **Event cards:** Cost badges (FREE green / $X yellow), recurring badge, "Sign Up" button when registration_url exists
- Renders: hero banner, metric cards (with Free Events count), side-by-side map + scrollable event cards

## Source Coverage (as of March 2026)

58 total sources (51 active), 667 events, 38 geocoded venues across 28 scouted municipalities.

### Confirmed Platforms
| Platform | Count | Examples |
|----------|-------|---------|
| RecDesk | ~19 | NK Rec, Warwick, Cranston, Coventry, Barrington, Cumberland, Lincoln, E. Providence, Johnston, Bristol, Burrillville, and more |
| LibCal | 7 | Cranston Library, Providence, Barrington, East Providence, Cumberland, N. Providence, West Warwick |
| WhoFi | 1 | North Kingstown Free Library |
| CivicPlus | 3 | SK Library, SK Rec, EG Rec |
| WordPress | 2 | Woonsocket Library, Tiverton Library |
| Custom/Drupal | 4+ | EG Library, Coventry Library, Westerly Library, Rogers Free Library, Portsmouth Library, Richmond Library |

### Key Wins from Municipality Scout
- East Providence Recreation (49 events via Playwright)
- Johnston Recreation (39 events via Playwright)
- 24 new sources discovered (5 libraries + 19 recreation departments)

## Deployment Architecture

```
GitHub (x-Delaque-x/LOOP, main branch)
    |
    v  (auto-deploy on push)
Streamlit Community Cloud  ──────>  Supabase PostgreSQL+PostGIS
    (app.py, light theme)           (session pooler, us-west-2)
```

- **Local ETL** runs against local Docker PostgreSQL, then data is migrated to Supabase
- **Production app** on Streamlit Cloud connects to Supabase via session pooler (IPv4, port 5432)
- **Secrets:** Local uses `.env`, cloud uses Streamlit secrets (`st.secrets`) — `_get_secret()` abstracts both
- **Theme:** `.streamlit/config.toml` forces `base = "light"` to match custom CSS

## UI Design
- **Light sidebar:** Lavender gradient with accent-colored selected pills, native Streamlit widget contrast
- **Sidebar controls:** ZIP code input, radius slider (1-50 miles), category pills, audience pills, sort (Closest/Soonest), date filter (Any/Today/This Weekend/Next 7 Days/Next 30 Days), cost filter (All/Free Only/Paid OK)
- **Sidebar forms:** URL submission (per municipality), feedback form (name optional + freetext)
- **Main area:** Hero banner, metric cards (Events/Venues/Free Events/Radius), side-by-side map + scrollable event cards
- **Coverage dashboard:** Expandable section showing all 39 municipalities with color-coded library/recreation status
- **Event cards:** Cost badge (FREE green / $X yellow), recurring badge, title, date/time/distance, tag pills, description snippet, "Sign Up" + "Get Directions" + "View Source" buttons
- **Mobile CSS:** `@media (max-width: 768px)` — wrapping metric cards, compact hero, smaller event cards
- **Master categories in `st.pills`:** Arts, Music, Food & Drink, Outdoors, Sports & Fitness, Education, STEM, Community, Nightlife, Family
- **Audience filters in `st.pills`:** Family, Kids (0-12), Teens (13-17), Adults (18+), Seniors (65+), All Ages (regex-escaped for filtering)

## Performance Optimizations
- **Concurrent fetching:** 6-worker ThreadPoolExecutor runs all adapters in parallel (~27s vs ~120s sequential)
- **Batch AI tagging:** 15 events per Gemini call (~9 calls vs ~130+ individual)
- **Weekly LibCal fetching:** 5 requests per site instead of 30 daily
- **Venue-level geocoding:** Geocode each venue once, reuse for all events at that location
- **Full harvest:** ~2-3 minutes (previously ~28 minutes)

## Key Design Patterns
- **Municipality-first model:** 39 RI municipalities as the organizing unit; sources linked via FK
- **Adapter pattern:** All scrapers inherit `BaseAdapter`, return uniform dicts
- **Normalized schema:** Municipality -> Source -> Venue -> Event with foreign keys
- **DB-driven registry:** `mass_harvest.py` reads active sources from `sources` table
- **Single source of truth:** `config.py` for constants, `sources` table for registry
- **Coverage tracking:** Municipality status tracks scouting progress (not_scouted/scouted/active/unreachable)
- **Crowdsourced discovery:** Users submit URLs via Streamlit form, admin reviews in url_submissions table
- **Graceful degradation:** App shows "Database Offline" instead of crashing when DB is down
- **PostGIS server-side filtering:** `ST_DWithin` instead of client-side distance calc
- **Migration safety:** `migrate_schema.py` auto-links sources to municipalities if table exists (order-independent)
- **Test suite:** 29 pytest smoke tests covering models, adapters, municipality registry, and pipeline imports
