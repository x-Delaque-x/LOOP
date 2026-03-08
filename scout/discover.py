"""
LOOP Source Discovery Scout
Automatically discovers library and recreation department calendar URLs
across Rhode Island, identifies their platform, and generates adapter configs.

Usage: python -m scout.discover
"""
import json
import logging
import time
from pathlib import Path

import requests
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scout")

client = genai.Client(api_key=GEMINI_API_KEY)

# Seed list of RI public libraries and recreation departments
# Source: RI Office of Library & Information Services + known town sites
RI_SEED_SOURCES = [
    # Public Libraries
    {"name": "North Kingstown Free Library", "type": "library", "website": "https://www.nklibrary.org"},
    {"name": "South Kingstown Public Library", "type": "library", "website": "https://www.skpl.org"},
    {"name": "Cranston Public Library", "type": "library", "website": "https://www.cranstonlibrary.org"},
    {"name": "Providence Public Library", "type": "library", "website": "https://www.provlib.org"},
    {"name": "Warwick Public Library", "type": "library", "website": "https://www.warwicklibrary.org"},
    {"name": "East Greenwich Free Library", "type": "library", "website": "https://www.eastgreenwichlibrary.org"},
    {"name": "Coventry Public Library", "type": "library", "website": "https://www.coventrypl.org"},
    {"name": "West Warwick Public Library", "type": "library", "website": "https://www.westwarwicklibrary.org"},
    {"name": "Narragansett Public Library", "type": "library", "website": "https://www.narragansettlibrary.org"},
    {"name": "Barrington Public Library", "type": "library", "website": "https://www.barringtonlibrary.org"},
    {"name": "East Providence Public Library", "type": "library", "website": "https://www.eastprovidencelibrary.org"},
    {"name": "Cumberland Public Library", "type": "library", "website": "https://www.cumberlandlibrary.org"},
    {"name": "North Providence Union Free Library", "type": "library", "website": "https://www.nprovlib.org"},
    {"name": "Pawtucket Public Library", "type": "library", "website": "https://www.pawtucketlibrary.org"},
    {"name": "Woonsocket Harris Public Library", "type": "library", "website": "https://www.woonsocketlibrary.org"},
    {"name": "Westerly Public Library", "type": "library", "website": "https://www.westerlylibrary.org"},
    {"name": "Smithfield Public Library", "type": "library", "website": "https://www.smithfieldpubliclibrary.org"},
    {"name": "Johnston Public Library", "type": "library", "website": "https://www.johnstonlibrary.org"},
    {"name": "Lincoln Public Library", "type": "library", "website": "https://www.lincolnpubliclibrary.org"},
    {"name": "Middletown Public Library", "type": "library", "website": "https://www.middletownpubliclibrary.org"},
    {"name": "Newport Public Library", "type": "library", "website": "https://www.newportlibraryri.org"},
    {"name": "Tiverton Public Library", "type": "library", "website": "https://www.tivertonlibrary.org"},
    {"name": "Bristol (Rogers Free Library)", "type": "library", "website": "https://www.rogersfreelibrary.org"},
    {"name": "Exeter Public Library", "type": "library", "website": "https://www.exeterpubliclibrary.org"},
    # Recreation Departments
    {"name": "North Kingstown Recreation", "type": "recreation", "website": "https://www.northkingstown.org/296/Recreation-Department"},
    {"name": "South Kingstown Recreation", "type": "recreation", "website": "https://www.southkingstownri.com/297/Recreation"},
    {"name": "Warwick Recreation", "type": "recreation", "website": "https://www.warwickri.gov/parks-recreation"},
    {"name": "Cranston Recreation", "type": "recreation", "website": "https://www.cranstonri.gov/recreation/"},
    {"name": "East Greenwich Recreation", "type": "recreation", "website": "https://www.eastgreenwichri.com/197/Parks-Recreation"},
    {"name": "Coventry Recreation", "type": "recreation", "website": "https://www.coventryri.org/parks-recreation"},
    {"name": "Narragansett Recreation", "type": "recreation", "website": "https://www.narragansettri.gov/155/Recreation"},
    {"name": "Barrington Recreation", "type": "recreation", "website": "https://www.barringtonri.gov/recreation"},
    {"name": "Cumberland Recreation", "type": "recreation", "website": "https://www.cumberlandri.org/recreation"},
    {"name": "Lincoln Recreation", "type": "recreation", "website": "https://www.lincolnri.org/recreation"},
]

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

OUTPUT_PATH = Path(__file__).parent / "ri_sources.json"


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
    # Truncate HTML to avoid token limits (keep first 15000 chars which covers headers + main content)
    truncated = html[:15000]

    prompt = f"Website: {name} ({website})\n\nHTML Content:\n{truncated}"

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"system_instruction": ANALYSIS_PROMPT},
        )
        text = response.text.strip()
        # Clean up markdown code fences if present
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
    # Try fetching common paths directly
    for path in common_paths:
        url = base + path
        try:
            resp = requests.head(url, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                return url
        except requests.RequestException:
            continue
    return None


def run_discovery():
    """Main discovery loop - scout all RI sources."""
    results = []

    log.info(f"Starting discovery of {len(RI_SEED_SOURCES)} sources...")

    for i, source in enumerate(RI_SEED_SOURCES):
        name = source["name"]
        website = source["website"]
        source_type = source["type"]

        log.info(f"[{i+1}/{len(RI_SEED_SOURCES)}] Scouting: {name}")

        # Fetch homepage
        html = fetch_page(website)
        if not html:
            results.append({
                "name": name,
                "type": source_type,
                "website": website,
                "platform": "Unreachable",
                "events_url": "",
                "api_endpoint": "",
                "has_events": False,
                "notes": "Could not reach website"
            })
            continue

        # Try to find events page
        events_page_url = try_find_events_page(website, html)
        events_html = html

        if events_page_url and events_page_url != website:
            log.info(f"  Found events page: {events_page_url}")
            page_html = fetch_page(events_page_url)
            if page_html:
                events_html = page_html

        # Analyze with Gemini
        analysis = analyze_site(name, website, events_html)

        result = {
            "name": name,
            "type": source_type,
            "website": website,
            "platform": analysis.get("platform", "Unknown"),
            "events_url": analysis.get("events_url", events_page_url or ""),
            "api_endpoint": analysis.get("api_endpoint", ""),
            "has_events": analysis.get("has_events", False),
            "notes": analysis.get("notes", "")
        }
        results.append(result)

        log.info(f"  Platform: {result['platform']} | Has Events: {result['has_events']}")

        # Rate limit: be polite to both websites and Gemini API
        time.sleep(2)

    # Write results
    OUTPUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    log.info(f"\nDiscovery complete. Results written to {OUTPUT_PATH}")

    # Summary
    platforms = {}
    for r in results:
        p = r["platform"]
        platforms[p] = platforms.get(p, 0) + 1

    log.info("\n--- Platform Summary ---")
    for platform, count in sorted(platforms.items(), key=lambda x: -x[1]):
        log.info(f"  {platform}: {count}")

    with_events = sum(1 for r in results if r["has_events"])
    log.info(f"\nSources with events: {with_events}/{len(results)}")

    return results


if __name__ == "__main__":
    run_discovery()
