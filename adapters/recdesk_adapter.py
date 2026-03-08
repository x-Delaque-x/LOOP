"""
RecDesk Adapter - Extracts events from recreation departments using the RecDesk platform.

RecDesk exposes a JSON calendar API at /Community/Calendar/GetCalendarItems
that returns events for a given month/year. A session must be established first
by visiting the Calendar page to get cookies.
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
        """Fetch events from the RecDesk Calendar JSON API."""
        session = requests.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        base = self.website

        # Strategy 1: Calendar JSON API
        events = self._fetch_calendar_api(session, base)
        if events:
            return events

        # Strategy 2: Scrape the Programs page
        events = self._scrape_programs_page(session, base)
        return events

    def _fetch_calendar_api(self, session: requests.Session, base: str) -> List[Dict]:
        """Fetch events from the RecDesk Calendar JSON API."""
        # Establish session by visiting the Calendar page
        try:
            cal_resp = session.get(f"{base}/Community/Calendar", timeout=15)
            if cal_resp.status_code != 200:
                log.debug(f"Calendar page unavailable for {self._name}")
                return []
        except Exception as e:
            log.debug(f"Failed to access {self._name} calendar: {e}")
            return []

        # Check that this is actually a RecDesk site with GetCalendarItems
        if "GetCalendarItems" not in cal_resp.text:
            log.debug(f"No GetCalendarItems endpoint found for {self._name}")
            return []

        # Fetch events for current month and next month
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

    def _parse_calendar_event(self, item: dict) -> Dict:
        """Parse a RecDesk calendar event from the JSON response."""
        title = item.get("EventName", "").strip()
        if not title:
            return {}

        # Parse dates
        event_date = ""
        event_time = ""

        start = item.get("StartDate", "")
        if start:
            try:
                # RecDesk dates are often in /Date(milliseconds)/ format
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

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description,
            "location_name": self._name,
            "source_url": f"{self.website}/Community/Calendar",
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

                # Look for program/event links
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
