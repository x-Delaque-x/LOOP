# LOOP Changelog

## [0.5.0] - 2026-03-08 — Platform Pivot
- **Rebranded** from "Local Opportunities and Outdoor Play" to **"Local Outings & Opportunities Platform"**
- **New MASTER_TAGS:** Arts, Music, Food & Drink, Outdoors, Sports & Fitness, Education, STEM, Community, Nightlife, Family
- **New AUDIENCE_TAGS** (replaces AGE_TAGS): Family, Kids (0-12), Teens (13-17), Adults (18+), Seniors (65+), All Ages
- Updated Gemini tagger prompt for general-audience event categorization
- Updated hero banner: "stay in the loop with events near you across Rhode Island"
- Sidebar label changed from "Filter by Age" to "Filter by Audience"
- Retagged all 667 events (local DB) with new categories

## [0.4.0] - 2026-03-08 — Stale Event Cleanup
- Added `cleanup_stale_events()` to harvest pipeline (Phase 6 of 7)
- Deletes events where `event_date_start` is before yesterday (1-day grace period)
- Skips recurring parents and events with NULL dates
- UI query now filters out past events (`event_date_start >= CURRENT_DATE - 1 day`)
- UI query now excludes expanded recurring children (`parent_event_id IS NULL`)
- Added `SUPABASE_URL` to `.env` for persistent production DB access

## [0.3.0] - 2026-03-07 — Parent-Friendly UX (Phases 1-4)
- **Phase 1 — Date normalization:** 6 new Event columns (`event_date_start`, `event_date_end`, `event_time_start`, `event_time_end`, `is_recurring`, `recurrence_pattern`). 14+ format date parser cascade.
- **Phase 2 — Cost & registration:** 3 new Event columns (`cost_text`, `cost_cents`, `registration_url`). Adapter-level extraction for RecDesk, LibCal, WhoFi, WordPress, Drupal. Cost parser with Free/dollar/varies detection. Tag-based cost inference fallback.
- **Phase 3 — UI overhaul:** Sort by Closest/Soonest. Date filter pills (Today/This Weekend/Next 7/30 Days). Cost filter (All/Free Only/Paid OK). Event cards with FREE/paid badges, recurring badges, Sign Up buttons. "Free Events" metric card.
- **Phase 4 — Recurring expansion:** `parent_event_id` FK column. `recurrence_expander.py` generates 4 weeks of concrete child events from "Every Saturday" patterns. Past children auto-cleaned.
- Migration scripts: `migrate_add_date_columns.py`, `migrate_add_cost_columns.py`, `migrate_add_recurrence_columns.py`
- All enrichment columns backfilled on both local and Supabase production DBs

## [0.2.0] - 2026-03-06 — Municipality Model & Deployment
- Normalized schema: Municipality -> Source -> Venue -> Event with foreign keys
- 39 RI municipalities seeded with library/recreation scouting status
- Municipality-driven scout (`py -m scout.discover`) with `--rescan` and `--town` flags
- Playwright integration for JS-rendered RecDesk sites (huge yield improvement)
- Feedback form and URL submission form in dashboard
- Connection resilience (`pool_pre_ping=True`, URL-encoded passwords)
- Light sidebar theme (lavender gradient) — stopped fighting Streamlit's dark mode
- Deployed to Streamlit Community Cloud + Supabase PostgreSQL+PostGIS
- 58 sources (51 active), 667 events, 38 geocoded venues, 28 municipalities scouted

## [0.1.0] - 2026-03-04 — Initial Release
- ETL pipeline: scout -> scrape -> AI tag (Gemini) -> PostGIS DB -> Streamlit dashboard
- 5 adapters: WhoFi, LibCal, RecDesk, WordPress, Drupal
- Gemini AI batch tagging (15 events/call)
- Concurrent fetching (6-worker ThreadPoolExecutor)
- PostGIS spatial queries (ST_DWithin, ST_Distance)
- Glass UI with hero banner, metric cards, map + event cards
- Venue-level geocoding via Nominatim
