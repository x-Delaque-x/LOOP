"""
RecDesk Adapter - Extracts events from recreation departments using the RecDesk platform.

Strategy order:
1. JSON Calendar API via requests (fast, no browser)
2. Playwright browser rendering (for JS-dependent calendar pages)
3. HTML Programs page scrape (last resort)

Playwright is needed because RecDesk calendar pages render events client-side
via JavaScript — requests alone gets an empty shell.
"""
import json
import logging
import re
from datetime import datetime
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
from adapters.base_adapter import BaseAdapter

log = logging.getLogger("adapters.recdesk")


class RecDeskAdapter(BaseAdapter):
    def __init__(self, name: str, website: str, events_url: str = ""):
        self._name = name
        self.website = website.rstrip("/")
        self.events_url = events_url or website

    @property
    def source_name(self) -> str:
        return self._name

    def fetch_events(self) -> List[Dict]:
        """Fetch events from RecDesk, trying API first, then Playwright."""
        session = requests.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        base = self.website

        # Strategy 1: Calendar JSON API (no browser needed)
        events = self._fetch_calendar_api(session, base)
        if events:
            return events

        # Strategy 2: Playwright browser rendering
        events = self._fetch_with_playwright(base)
        if events:
            return events

        # Strategy 3: Scrape the Programs page
        events = self._scrape_programs_page(session, base)
        return events

    def _fetch_calendar_api(self, session: requests.Session, base: str) -> List[Dict]:
        """Fetch events from the RecDesk Calendar JSON API."""
        try:
            cal_resp = session.get(f"{base}/Community/Calendar", timeout=15)
            if cal_resp.status_code != 200:
                log.debug(f"Calendar page unavailable for {self._name}")
                return []
        except Exception as e:
            log.debug(f"Failed to access {self._name} calendar: {e}")
            return []

        if "GetCalendarItems" not in cal_resp.text:
            log.debug(f"No GetCalendarItems endpoint found for {self._name}")
            return []

        api_url = f"{base}/Community/Calendar/GetCalendarItems"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{base}/Community/Calendar",
        }

        events = []
        now = datetime.now()

        for month_offset in range(3):
            month = now.month + month_offset
            year = now.year
            if month > 12:
                month -= 12
                year += 1

            payload = {
                "SelectedMonth": str(month),
                "SelectedYear": str(year),
            }

            try:
                resp = session.post(api_url, data=json.dumps(payload),
                                    headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                ct = resp.headers.get("content-type", "")
                if "json" not in ct:
                    log.debug(f"Non-JSON response from {self._name} calendar API")
                    continue

                data = resp.json()
                for item in data.get("Events", []):
                    event = self._parse_calendar_event(item)
                    if event:
                        events.append(event)

            except Exception as e:
                log.debug(f"Calendar API failed for {self._name} ({month}/{year}): {e}")
                continue

        log.info(f"Fetched {len(events)} events from {self._name} (RecDesk Calendar API)")
        return events

    def _fetch_with_playwright(self, base: str) -> List[Dict]:
        """Use Playwright to render the JS calendar and extract events."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.debug("Playwright not installed, skipping browser rendering")
            return []

        cal_url = f"{base}/Community/Calendar"
        events = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_timeout(30000)

                log.info(f"  Playwright: loading {self._name} calendar...")
                page.goto(cal_url, wait_until="networkidle")

                # Wait for calendar events to render
                page.wait_for_timeout(2000)

                # Try to find rendered calendar event elements
                events = self._extract_from_rendered_page(page, base)

                # If no events on current view, try clicking next month
                if not events:
                    try:
                        next_btn = page.locator("a.fc-next-button, .fc-next-button, [title='Next']").first
                        if next_btn.is_visible():
                            next_btn.click()
                            page.wait_for_timeout(2000)
                            events = self._extract_from_rendered_page(page, base)
                    except Exception:
                        pass

                browser.close()

        except Exception as e:
            log.warning(f"Playwright failed for {self._name}: {e}")
            return []

        log.info(f"Fetched {len(events)} events from {self._name} (Playwright)")
        return events

    def _extract_from_rendered_page(self, page, base: str) -> List[Dict]:
        """Extract events from the Playwright-rendered DOM."""
        events = []
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # RecDesk calendar events appear as FullCalendar event elements
        # or as list items in the calendar view
        event_selectors = [
            ".fc-event",                    # FullCalendar events
            ".fc-event-container a",        # FullCalendar event links
            ".calendar-event",              # Generic calendar events
            ".event-item",                  # Event list items
            "[class*='CalendarItem']",      # RecDesk-specific
        ]

        seen_titles = set()
        for selector in event_selectors:
            elements = soup.select(selector)
            for el in elements:
                title = el.get_text(strip=True)
                # Clean up title — remove time prefixes like "10:00 AM - "
                title = re.sub(r'^\d{1,2}:\d{2}\s*(?:AM|PM)\s*[-–]\s*', '', title).strip()
                title = re.sub(r'^\d{1,2}:\d{2}\s*(?:AM|PM)\s*', '', title).strip()

                if not title or len(title) < 3 or title in seen_titles:
                    continue
                seen_titles.add(title)

                # Try to extract date from data attributes or parent
                event_date = ""
                event_time = ""

                # FullCalendar stores dates in data attributes
                date_attr = el.get("data-date") or el.parent.get("data-date", "") if el.parent else ""
                if date_attr:
                    event_date = date_attr[:10]  # YYYY-MM-DD

                # Extract time from the element text
                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM))', el.get_text())
                if time_match:
                    event_time = time_match.group(1)

                href = el.get("href", "")
                from urllib.parse import urljoin
                source_url = urljoin(base, href) if href else f"{base}/Community/Calendar"

                events.append({
                    "title": title,
                    "event_date": event_date,
                    "event_time": event_time,
                    "description": "",
                    "location_name": self._name,
                    "source_url": source_url,
                })

            if events:
                break

        # Also try intercepting any JSON data embedded in the page
        if not events:
            events = self._extract_json_from_page(soup, base)

        return events

    def _extract_json_from_page(self, soup, base: str) -> List[Dict]:
        """Try to find calendar event JSON embedded in script tags."""
        events = []
        for script in soup.find_all("script"):
            text = script.string or ""
            # Look for event arrays in script content
            for match in re.finditer(r'"EventName"\s*:\s*"([^"]+)"', text):
                title = match.group(1).strip()
                if title:
                    events.append({
                        "title": title,
                        "event_date": "",
                        "event_time": "",
                        "description": "",
                        "location_name": self._name,
                        "source_url": f"{base}/Community/Calendar",
                    })
        return events

    def _parse_calendar_event(self, item: dict) -> Dict:
        """Parse a RecDesk calendar event from the JSON response."""
        title = item.get("EventName", "").strip()
        if not title:
            return {}

        event_date = ""
        event_time = ""

        start = item.get("StartDate", "")
        if start:
            try:
                if "/Date(" in str(start):
                    ms = int(re.search(r"/Date\((\d+)", str(start)).group(1))
                    dt = datetime.fromtimestamp(ms / 1000)
                else:
                    dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                event_date = dt.strftime("%Y-%m-%d")
                event_time = dt.strftime("%I:%M %p")
            except (ValueError, AttributeError):
                event_date = str(start)

        facility = item.get("FacilityName", "")
        description = facility if facility else ""

        # Extract cost — RecDesk uses varying field names
        cost_text = ""
        for key in ("Fee", "Cost", "Price", "FeeAmount", "EventFee"):
            val = item.get(key)
            if val is not None and str(val).strip():
                cost_text = str(val).strip()
                break

        # Extract registration URL
        reg_url = ""
        for key in ("RegistrationUrl", "RegisterUrl", "RegistrationLink"):
            val = item.get(key)
            if val and str(val).strip().startswith("http"):
                reg_url = str(val).strip()
                break

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description,
            "location_name": self._name,
            "source_url": f"{self.website}/Community/Calendar",
            "cost_text": cost_text,
            "registration_url": reg_url,
        }

    def _scrape_programs_page(self, session: requests.Session, base: str) -> List[Dict]:
        """Fallback: scrape the Programs page for any static content."""
        events = []

        for path in ["/Community/Program", "/Community/Calendar"]:
            try:
                resp = session.get(f"{base}{path}", timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                for link in soup.find_all("a", href=re.compile(r"/Community/Program/\d+")):
                    title = link.get_text(strip=True)
                    if title and len(title) > 3:
                        from urllib.parse import urljoin
                        events.append({
                            "title": title,
                            "event_date": "",
                            "event_time": "",
                            "description": "",
                            "location_name": self._name,
                            "source_url": urljoin(base, link["href"]),
                        })

                if events:
                    break

            except Exception as e:
                log.debug(f"Failed to scrape {base}{path}: {e}")

        log.info(f"Scraped {len(events)} events from {self._name} (RecDesk HTML)")
        return events
