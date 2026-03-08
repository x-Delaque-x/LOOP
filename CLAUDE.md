# LOOP - Claude Code Project Instructions

## Environment
- **Windows 11**, Git Bash shell. Use `py` not `python` (Windows App Execution Alias blocks `python`).
- **venv** at `.venv/`. Activate: `source .venv/Scripts/activate`
- **Docker Desktop** must be started manually. The PostGIS container is `loop-db` (pre-existing, NOT from our docker-compose.yml).
- **DB creds** are in `.env` (user: `postgres`, password: `loop_secure_2026`, db: `loop_db`, port: 5432).

## Code Conventions
- Use `google.genai` SDK (the `google-genai` package). The old `google.generativeai` package is deprecated.
- `config.py` is the single source of truth for constants: APP_NAME, MASTER_TAGS, AGE_TAGS, DATABASE_URL, GEMINI_MODEL.
- `database_manager.py` exports `SessionLocal`, `Source`, `Venue`, `Event`, and `GoldenEvent` (alias for Event).
- Normalized schema: `sources` -> `venues` -> `events` with foreign keys. `app.py` JOINs events to venues.
- Adapters inherit from `adapters/base_adapter.py:BaseAdapter` and implement `fetch_events() -> List[Dict]` and `source_name` property.
- Event dicts use keys: `title`, `event_date`, `event_time`, `description`, `location_name`, `source_url`.
- Upsert natural key: `(title, event_date, venue_id)`.
- Batch tagging: `tag_events_batch()` sends 15 events per Gemini call. Use this instead of `tag_event()` for bulk operations.

## Key Workflows
- **Scout:** `py -m scout.discover` — scans RI sources, writes `scout/ri_sources.json`
- **Harvest:** `py mass_harvest.py` — concurrent fetch (6 workers), batch AI tag, upsert, geocode (~2-3 min)
- **Dashboard:** `streamlit run app.py` — Streamlit UI with PostGIS spatial queries
- **Migration:** `py migrate_schema.py` — one-time: seeds sources/venues from ri_sources.json, migrates golden_events

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
