# LOOP - Claude Code Project Instructions

## Environment
- **Windows 11**, Git Bash shell. Use `py` not `python` (Windows App Execution Alias blocks `python`).
- **venv** at `.venv/`. Activate: `source .venv/Scripts/activate`
- **Local DB:** Docker Desktop must be started manually. PostGIS container is `loop-db` (pre-existing, NOT from docker-compose.yml). Creds in `.env` (user: `postgres`, password: `loop_secure_2026`, db: `loop_db`, port: 5432).
- **Production DB:** Supabase (PostgreSQL + PostGIS), region `us-west-2`. Connection via session pooler: `aws-0-us-west-2.pooler.supabase.com:5432`. Creds in Streamlit Cloud secrets.
- **Deployment:** Streamlit Community Cloud auto-deploys from `main` branch of `github.com/x-Delaque-x/LOOP`.

## Code Conventions
- Use `google.genai` SDK (the `google-genai` package). The old `google.generativeai` package is deprecated.
- `config.py` is the single source of truth for constants: APP_NAME, MASTER_TAGS, AGE_TAGS, DATABASE_URL, GEMINI_MODEL. Uses `_get_secret()` helper to support both `.env` (local) and `st.secrets` (Streamlit Cloud).
- `database_manager.py` exports `SessionLocal`, `Municipality`, `Source`, `Venue`, `Event`, `URLSubmission`, `Feedback`, and `GoldenEvent` (alias for Event). Engine uses `pool_pre_ping=True`.
- Normalized schema: `municipalities` -> `sources` -> `venues` -> `events` with foreign keys. `app.py` JOINs events to venues.
- Municipality model: 39 RI municipalities as the organizing unit. Sources link to municipalities via `municipality_id` FK.
- Adapters inherit from `adapters/base_adapter.py:BaseAdapter` and implement `fetch_events() -> List[Dict]` and `source_name` property.
- Event dicts use keys: `title`, `event_date`, `event_time`, `description`, `location_name`, `source_url`. Optional: `cost_text`, `registration_url`.
- Upsert natural key: `(title, event_date, venue_id)`.
- Batch tagging: `tag_events_batch()` sends 15 events per Gemini call. Use this instead of `tag_event()` for bulk operations.
- Event model has 10 enrichment columns: 6 date/time (`event_date_start`, `event_date_end`, `event_time_start`, `event_time_end`, `is_recurring`, `recurrence_pattern`), 3 cost (`cost_text`, `cost_cents`, `registration_url`), 1 recurring expansion (`parent_event_id`).

## Key Workflows
- **Scout:** `py -m scout.discover` — municipality-driven discovery, scouts unscouted towns. Flags: `--rescan`, `--town "Name"`
- **Harvest:** `py mass_harvest.py` — concurrent fetch (6 workers), batch AI tag, upsert, normalize dates, parse cost, expand recurring, geocode (~2-3 min). Some adapters use Playwright for JS-rendered pages.
- **Dashboard:** `streamlit run app.py` — Streamlit UI with PostGIS spatial queries, sort/date/cost filters, coverage dashboard, URL/feedback submission forms
- **Tests:** `py -m pytest tests/ -v` — 29 smoke tests (models, adapters, municipalities, pipeline, cost parser)
- **Migrations** (one-time, safe to re-run):
  - `py migrate_add_date_columns.py` — date normalization columns + backfill
  - `py migrate_add_cost_columns.py` — cost/registration columns + backfill from tags
  - `py migrate_add_recurrence_columns.py` — parent_event_id + expand recurring
- **Seed Migrations** (run in either order — `migrate_schema.py` auto-links sources to municipalities if table exists):
  - `py migrate_schema.py` — seeds sources/venues from ri_sources.json
  - `py migrate_municipalities.py` — seeds 39 municipalities, links existing sources

## Scout URL Resolution
The scout uses a 3-tier priority for finding source URLs (`find_source_url()`):
1. Existing DB source (Source.website for that municipality + type)
2. `KNOWN_SEEDS` bootstrap fallback (hardcoded, only for fresh installs)
3. URL pattern guessing (`{town}library.org`, `{town}.recdesk.com`, etc.)

## Deployment
- **GitHub:** Public repo `x-Delaque-x/LOOP`, branch `main`
- **Streamlit Cloud:** Auto-deploys on push to `main`. Secrets in Streamlit dashboard (TOML format with `DATABASE_URL`).
- **Supabase:** Free-tier PostgreSQL+PostGIS. Session pooler (port 5432) for cloud; direct connection for local ETL.
- **Theme:** `.streamlit/config.toml` forces `base = "light"` to match custom CSS.
- **Password note:** Supabase password contains `!` — must be URL-encoded as `%21` in connection strings.

## Documentation Policy
After significant changes, update these files:
1. `CLAUDE.md` (this file) — project instructions for Claude Code
2. `ARCHITECTURE.md` — technical architecture and data flow
3. `README.md` — user-facing setup and usage
4. `memory/MEMORY.md` (at `~/.claude/projects/c--Dev-LOOP/memory/`) — cross-session learnings

## Don'ts
- Never hardcode API keys or DB credentials — always use `.env` via `config.py`
- Never modify the `GoldenEvent` model or `SessionLocal` export signature without updating `app.py`
- Never use `google.generativeai` — it's deprecated, use `google.genai`
- Never commit `.env` (it's in `.gitignore`)
