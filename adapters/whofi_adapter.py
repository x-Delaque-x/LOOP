"""
WhoFi Adapter - Extracts events from libraries using the WhoFi platform.

WhoFi renders event listings as HTML cards on the /calendar/ page.
Each event has a link to /calendar/event/{id} with title, description,
date, time, and category information embedded in the page.
"""
import logging
import re
from datetime import datetime
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
from adapters.base_adapter import BaseAdapter

log = logging.getLogger("adapters.whofi")


class WhoFiAdapter(BaseAdapter):
    def __init__(self, name: str, website: str, api_endpoint: str = "",
                 events_url: str = ""):
        self._name = name
        self.website = website
        self.events_url = events_url or website
        self.api_endpoint = api_endpoint

    @property
    def source_name(self) -> str:
        return self._name

    def fetch_events(self) -> List[Dict]:
        """Fetch events by scraping the WhoFi calendar page."""
        calendar_url = self.events_url
        if not calendar_url or "whofi.com" not in calendar_url:
            # Try to construct the WhoFi calendar URL
            calendar_url = self.website
            if "whofi.com" not in calendar_url:
                log.warning(f"No WhoFi calendar URL for {self._name}")
                return []

        if not calendar_url.rstrip("/").endswith("/calendar"):
            calendar_url = calendar_url.rstrip("/") + "/calendar/"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            resp = requests.get(calendar_url, headers=headers, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            log.error(f"Failed to fetch WhoFi calendar for {self._name}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        events = []
        seen_ids = set()

        # Find all event links (pattern: /calendar/event/{id})
        event_links = soup.find_all("a", href=re.compile(r"/calendar/event/\d+"))

        for link in event_links:
            href = link.get("href", "")
            # Extract event ID to deduplicate
            m = re.search(r"/calendar/event/(\d+)", href)
            if not m:
                continue
            event_id = m.group(1)
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            title = link.get_text(strip=True)
            # Skip non-title links like "More Details" or "Register Now"
            if not title or title.lower() in ("more details", "register now", "register"):
                continue

            # Build the full event URL
            from urllib.parse import urljoin
            event_url = urljoin(calendar_url, href)

            # Find the parent container to extract date/description
            container = link.find_parent("div", class_="col-md-6") or link.find_parent("div", class_="d-flex")
            if not container:
                # Try broader parent search
                container = link.find_parent("div", recursive=True)

            event_date = ""
            event_time = ""
            description = ""

            if container:
                # Get the text content of the container area
                text_blocks = container.find_all("p", class_="fw-bold")
                for block in text_blocks:
                    text = block.get_text(strip=True)
                    # Check if this is the description (longer text)
                    if len(text) > 50 and not any(day in text for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
                        description = text
                    # Check for day/date pattern
                    day_match = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(\w+\s+\d+\w*)", text)
                    if day_match:
                        event_date = day_match.group(0)

                # Look for time pattern
                time_blocks = container.find_all("p", class_="fs-5")
                for block in time_blocks:
                    text = block.get_text(strip=True)
                    time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*-\s*(\d{1,2}:\d{2}\s*(?:am|pm))", text, re.I)
                    if time_match:
                        event_time = f"{time_match.group(1)} - {time_match.group(2)}"
                    elif re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", text):
                        event_date = event_date or text

            events.append({
                "title": title.strip(),
                "event_date": event_date,
                "event_time": event_time,
                "description": description[:500] if description else "",
                "location_name": self._name,
                "source_url": event_url,
            })

        log.info(f"Fetched {len(events)} events from {self._name} (WhoFi HTML)")
        return events
