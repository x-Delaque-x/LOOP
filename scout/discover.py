"""
LOOP Source Discovery Scout
Municipality-driven discovery: reads all 39 RI municipalities from the database,
scouts each one for library and recreation department calendar URLs, identifies
their platform, and creates Source records linked to the municipality.

Usage: python -m scout.discover [--rescan] [--town "Town Name"]
"""
import json
import logging
import time
import sys
from pathlib import Path

import requests
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL
from database_manager import SessionLocal, Source, Municipality, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scout")

client = genai.Client(api_key=GEMINI_API_KEY)

# Bootstrap fallback URLs — only used when the DB has no existing source for a municipality.
# Once a source is in the DB, its website field is used instead (see find_source_url).
KNOWN_SEEDS = {
    "Barrington": {"library": "https://www.barringtonlibrary.org", "recreation": "https://www.barringtonri.gov/recreation"},
    "Bristol": {"library": "https://www.rogersfreelibrary.org"},
    "Coventry": {"library": "https://www.coventrypl.org", "recreation": "https://www.coventryri.org/parks-recreation"},
    "Cranston": {"library": "https://www.cranstonlibrary.org", "recreation": "https://www.cranstonri.gov/recreation/"},
    "Cumberland": {"library": "https://www.cumberlandlibrary.org", "recreation": "https://www.cumberlandri.org/recreation"},
    "East Greenwich": {"library": "https://www.eastgreenwichlibrary.org", "recreation": "https://www.eastgreenwichri.com/197/Parks-Recreation"},
    "East Providence": {"library": "https://www.eastprovidencelibrary.org"},
    "Exeter": {"library": "https://www.exeterpubliclibrary.org"},
    "Johnston": {"library": "https://www.johnstonlibrary.org"},
    "Lincoln": {"library": "https://www.lincolnpubliclibrary.org", "recreation": "https://www.lincolnri.org/recreation"},
    "Middletown": {"library": "https://www.middletownpubliclibrary.org"},
    "Narragansett": {"library": "https://www.narragansettlibrary.org", "recreation": "https://www.narragansettri.gov/155/Recreation"},
    "Newport": {"library": "https://www.newportlibraryri.org"},
    "North Kingstown": {"library": "https://www.nklibrary.org", "recreation": "https://www.northkingstown.org/296/Recreation-Department"},
    "North Providence": {"library": "https://www.nprovlib.org"},
    "Pawtucket": {"library": "https://www.pawtucketlibrary.org"},
    "Providence": {"library": "https://www.provlib.org"},
    "Smithfield": {"library": "https://www.smithfieldpubliclibrary.org"},
    "South Kingstown": {"library": "https://www.skpl.org", "recreation": "https://www.southkingstownri.com/297/Recreation"},
    "Tiverton": {"library": "https://www.tivertonlibrary.org"},
    "Warwick": {"library": "https://www.warwicklibrary.org", "recreation": "https://www.warwickri.gov/parks-recreation"},
    "West Warwick": {"library": "https://www.westwarwicklibrary.org"},
    "Westerly": {"library": "https://www.westerlylibrary.org"},
    "Woonsocket": {"library": "https://www.woonsocketlibrary.org"},
}

ANALYSIS_PROMPT = """You are a web scraping expert analyzing a website for event calendar data.

Given the HTML content of a website, identify:
1. **platform**: The calendar/events platform used. Common ones include:
   - "LibCal" (Springshare LibCal - look for libcal.com URLs, "Powered by LibCal", springshare scripts)
   - "WhoFi" (look for whofi.com references, JSON API endpoints)
   - "RecDesk" (look for recdesk.com URLs, RecDesk branding)
   - "Eventbrite" (look for eventbrite.com embeds)
   - "Google Calendar" (look for calendar.google.com embeds)
   - "WordPress Events" (look for tribe-events, Events Calendar plugin)
   - "Custom" (no recognizable platform)
   - "Unknown" (can't determine from the HTML)

2. **events_url**: The URL of the events/calendar page (may be on a different path than the homepage)
3. **api_endpoint**: Any JSON API endpoint found (look for AJAX calls, data-src attributes, script URLs with /api/ or /feed/)
4. **has_events**: true/false - whether this site appears to have a public events listing
5. **notes**: Any useful observations about how to scrape this source

Respond with ONLY a JSON object, no markdown formatting:
{"platform": "...", "events_url": "...", "api_endpoint": "...", "has_events": true/false, "notes": "..."}
"""

MULTI_BRANCH_PROMPT = """You are analyzing a public library system website for a large city.

This city may have MULTIPLE library branches. Analyze the HTML and list ALL library branches you can find.
For each branch, provide:
- name: The full branch name
- events_url: The events/calendar URL for that branch (if different from main)

Respond with ONLY a JSON array, no markdown formatting:
[{"name": "Main Library", "events_url": "..."}, {"name": "Branch Name", "events_url": "..."}]

If you can only find one library, return a single-element array.
"""

OUTPUT_PATH = Path(__file__).parent / "ri_sources.json"

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


def fetch_page(url, timeout=15):
    """Fetch a web page and return its HTML content."""
    headers = {
        "User-Agent": "LOOP-Scout/1.0 (Educational Research; Rhode Island Family Events)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log.warning(f"  Failed to fetch {url}: {e}")
        return None


def analyze_site(name, website, html):
    """Use Gemini to analyze a website's HTML and identify its calendar platform."""
    truncated = html[:15000]
    prompt = f"Website: {name} ({website})\n\nHTML Content:\n{truncated}"

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"system_instruction": ANALYSIS_PROMPT},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        if text.startswith("json"):
            text = text[4:]
        return json.loads(text.strip())
    except (json.JSONDecodeError, Exception) as e:
        log.warning(f"  Gemini analysis failed for {name}: {e}")
        return {
            "platform": "Unknown",
            "events_url": "",
            "api_endpoint": "",
            "has_events": False,
            "notes": f"Analysis failed: {e}"
        }


def try_find_events_page(website, html):
    """Look for common events page paths if the homepage doesn't have events."""
    common_paths = ["/events", "/calendar", "/programs", "/activities"]
    base = website.rstrip("/")
    for path in common_paths:
        url = base + path
        if path in html.lower() or f'href="{path}"' in html.lower():
            return url
    for path in common_paths:
        url = base + path
        try:
            resp = requests.head(url, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                return url
        except requests.RequestException:
            continue
    return None


def find_source_url(session, municipality, source_type):
    """Find a URL for a municipality's library or recreation department.

    Priority: 1) existing DB source, 2) KNOWN_SEEDS fallback, 3) URL pattern guessing.
    """
    # 1. Check if there's already a source in the DB for this municipality + type
    existing = session.query(Source).filter_by(
        municipality_id=municipality.id, type=source_type
    ).first()
    if existing and existing.website:
        return existing.website

    # 2. Check KNOWN_SEEDS fallback (for bootstrapping new installs)
    seeds = KNOWN_SEEDS.get(municipality.name, {})
    if source_type in seeds:
        return seeds[source_type]

    # 3. Try common URL patterns
    slug = municipality.name.lower().replace(" ", "")

    if source_type == "library":
        candidates = [
            f"https://www.{slug}library.org",
            f"https://www.{slug}publiclibrary.org",
            f"https://www.{slug}pl.org",
            f"https://{slug}.libcal.com",
        ]
    else:
        candidates = [
            f"https://{slug}.recdesk.com",
            f"https://www.{slug}ri.gov/parks-recreation",
            f"https://www.{slug}ri.com/recreation",
        ]

    for url in candidates:
        try:
            resp = requests.head(url, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                return url
        except requests.RequestException:
            continue

    return None


def scout_source(session, municipality, source_type, website):
    """Scout a single source URL, analyze it, and create/update a Source record."""
    name_suffix = "Public Library" if source_type == "library" else "Recreation"
    source_name = f"{municipality.name} {name_suffix}"

    # Special names for known sources
    special_names = {
        ("Bristol", "library"): "Bristol (Rogers Free Library)",
        ("Woonsocket", "library"): "Woonsocket Harris Public Library",
        ("North Kingstown", "library"): "North Kingstown Free Library",
        ("East Greenwich", "library"): "East Greenwich Free Library",
        ("North Providence", "library"): "North Providence Union Free Library",
    }
    source_name = special_names.get((municipality.name, source_type), source_name)

    # Check if source already exists
    existing = session.query(Source).filter_by(name=source_name).first()
    if existing:
        log.info(f"  Source already exists: {source_name}")
        return existing

    log.info(f"  Scouting {source_type}: {website}")

    html = fetch_page(website)
    if not html:
        log.warning(f"  Unreachable: {website}")
        return None

    # Try to find events page
    events_page_url = try_find_events_page(website, html)
    events_html = html
    if events_page_url and events_page_url != website:
        log.info(f"    Found events page: {events_page_url}")
        page_html = fetch_page(events_page_url)
        if page_html:
            events_html = page_html

    # Analyze with Gemini
    analysis = analyze_site(source_name, website, events_html)

    platform = analysis.get("platform", "Unknown")
    adapter_name = PLATFORM_TO_ADAPTER.get(platform.lower(), "drupal")
    events_url = analysis.get("events_url", events_page_url or "")
    api_endpoint = analysis.get("api_endpoint", "")

    # Clean garbage values
    if events_url and ("Not found" in events_url or "None found" in events_url):
        events_url = ""
    if api_endpoint and ("Not found" in api_endpoint or "None found" in api_endpoint):
        api_endpoint = ""

    source = Source(
        name=source_name,
        type=source_type,
        website=website,
        platform=platform,
        events_url=events_url,
        api_endpoint=api_endpoint,
        adapter_name=adapter_name,
        is_active=analysis.get("has_events", False),
        notes=analysis.get("notes", ""),
        municipality_id=municipality.id,
    )
    session.add(source)
    session.commit()

    log.info(f"    Platform: {platform} | Active: {source.is_active}")
    time.sleep(2)  # Rate limit

    return source


def scout_municipality(session, municipality, rescan=False):
    """Scout a single municipality for library and recreation sources."""
    log.info(f"\n--- {municipality.name} (pop. {municipality.population:,}, {municipality.county} County) ---")

    # Scout library
    if municipality.has_library and (municipality.library_status == "not_scouted" or rescan):
        url = find_source_url(session, municipality, "library")
        if url:
            source = scout_source(session, municipality, "library", url)
            if source:
                municipality.library_status = "active" if source.is_active else "scouted"
            else:
                municipality.library_status = "unreachable"
        else:
            log.info(f"  No library URL found for {municipality.name}")
            municipality.library_status = "unreachable"
        session.commit()

    # Scout recreation
    if municipality.has_recreation and (municipality.recreation_status == "not_scouted" or rescan):
        url = find_source_url(session, municipality, "recreation")
        if url:
            source = scout_source(session, municipality, "recreation", url)
            if source:
                municipality.recreation_status = "active" if source.is_active else "scouted"
            else:
                municipality.recreation_status = "unreachable"
        else:
            log.info(f"  No recreation URL found for {municipality.name}")
            municipality.recreation_status = "unreachable"
        session.commit()


def export_results(session):
    """Export current sources to ri_sources.json for backward compatibility."""
    sources = session.query(Source).all()
    results = []
    for s in sources:
        results.append({
            "name": s.name,
            "type": s.type,
            "website": s.website,
            "platform": s.platform or "Unknown",
            "events_url": s.events_url or "",
            "api_endpoint": s.api_endpoint or "",
            "has_events": s.is_active,
            "notes": s.notes or "",
        })

    OUTPUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    log.info(f"Exported {len(results)} sources to {OUTPUT_PATH}")


def run_discovery(rescan=False, town_filter=None):
    """Main discovery loop — scout municipalities that haven't been scouted yet."""
    init_db()
    session = SessionLocal()

    query = session.query(Municipality).order_by(Municipality.name)
    if town_filter:
        query = query.filter(Municipality.name.ilike(f"%{town_filter}%"))

    municipalities = query.all()
    if not municipalities:
        log.warning("No municipalities found. Run migrate_municipalities.py first.")
        session.close()
        return

    # Count what needs scouting
    to_scout = [m for m in municipalities if
                (m.has_library and (m.library_status == "not_scouted" or rescan)) or
                (m.has_recreation and (m.recreation_status == "not_scouted" or rescan))]

    log.info(f"Municipalities: {len(municipalities)} total, {len(to_scout)} to scout")

    for i, muni in enumerate(municipalities):
        needs_scout = (
            (muni.has_library and (muni.library_status == "not_scouted" or rescan)) or
            (muni.has_recreation and (muni.recreation_status == "not_scouted" or rescan))
        )
        if needs_scout:
            scout_municipality(session, muni, rescan=rescan)

    # Export results
    export_results(session)

    # Summary
    log.info("\n" + "=" * 60)
    log.info("Discovery Summary")
    log.info("=" * 60)

    all_munis = session.query(Municipality).order_by(Municipality.name).all()
    lib_active = sum(1 for m in all_munis if m.library_status == "active")
    lib_scouted = sum(1 for m in all_munis if m.library_status == "scouted")
    lib_unscouted = sum(1 for m in all_munis if m.library_status == "not_scouted")
    rec_active = sum(1 for m in all_munis if m.recreation_status == "active")
    rec_scouted = sum(1 for m in all_munis if m.recreation_status == "scouted")
    rec_unscouted = sum(1 for m in all_munis if m.recreation_status == "not_scouted")

    log.info(f"Libraries:   {lib_active} active, {lib_scouted} scouted, {lib_unscouted} not scouted")
    log.info(f"Recreation:  {rec_active} active, {rec_scouted} scouted, {rec_unscouted} not scouted")

    total_sources = session.query(Source).count()
    active_sources = session.query(Source).filter_by(is_active=True).count()
    log.info(f"Total sources: {total_sources} ({active_sources} active)")

    session.close()


if __name__ == "__main__":
    rescan = "--rescan" in sys.argv
    town = None
    if "--town" in sys.argv:
        idx = sys.argv.index("--town")
        if idx + 1 < len(sys.argv):
            town = sys.argv[idx + 1]
    run_discovery(rescan=rescan, town_filter=town)
