"""
WordPress Events Adapter - Extracts events from WordPress sites.

Targets sites using Modern Events Calendar (MEC) or The Events Calendar plugins.
Scrapes the /events/ page directly since WP event plugins render HTML server-side.
"""
import logging
import re
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from adapters.base_adapter import BaseAdapter

log = logging.getLogger("adapters.wordpress")


class WordPressAdapter(BaseAdapter):
    def __init__(self, name: str, website: str, events_url: str = ""):
        self._name = name
        self.website = website
        self.events_url = events_url or (website.rstrip("/") + "/events/")

    @property
    def source_name(self) -> str:
        return self._name

    def fetch_events(self) -> List[Dict]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        events = []

        # Try the events page
        try:
            resp = requests.get(self.events_url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.error(f"Failed to fetch {self._name}: {e}")
            return []

        # Strategy 1: Modern Events Calendar (MEC) selectors
        mec_events = soup.select(".mec-event-article, .mec-event-listing .event-card, .mec-wrap .mec-event")
        if mec_events:
            for el in mec_events:
                event = self._parse_mec_event(el)
                if event:
                    events.append(event)
            log.info(f"Fetched {len(events)} MEC events from {self._name}")
            return events

        # Strategy 2: The Events Calendar selectors
        tec_events = soup.select(".tribe-events-calendar-list__event, .tribe_events .type-tribe_events")
        if tec_events:
            for el in tec_events:
                event = self._parse_tec_event(el)
                if event:
                    events.append(event)
            log.info(f"Fetched {len(events)} TEC events from {self._name}")
            return events

        # Strategy 3: Generic event-like content
        events = self._parse_generic_events(soup)
        log.info(f"Fetched {len(events)} generic events from {self._name}")
        return events

    def _parse_mec_event(self, el) -> Dict:
        title_el = el.select_one(".mec-event-title a, h2 a, h3 a, h4 a")
        if not title_el:
            return {}

        title = title_el.get_text(strip=True)
        source_url = urljoin(self.events_url, title_el.get("href", ""))

        date_el = el.select_one(".mec-event-date, .mec-date, time, .mec-start-date")
        date_str = date_el.get_text(strip=True) if date_el else ""
        event_date, event_time = self._parse_date_text(date_str)

        desc_el = el.select_one(".mec-event-description, .mec-event-content, p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description[:500],
            "location_name": self._name,
            "source_url": source_url,
        }

    def _parse_tec_event(self, el) -> Dict:
        title_el = el.select_one(".tribe-events-calendar-list__event-title a, .tribe-event-url a, h2 a")
        if not title_el:
            return {}

        title = title_el.get_text(strip=True)
        source_url = urljoin(self.events_url, title_el.get("href", ""))

        date_el = el.select_one("time, .tribe-event-schedule-details, .tribe-events-abbr")
        date_str = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
        event_date, event_time = self._parse_date_text(date_str)

        desc_el = el.select_one(".tribe-events-calendar-list__event-description p, .tribe-events-list-event-description p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description[:500],
            "location_name": self._name,
            "source_url": source_url,
        }

    def _parse_generic_events(self, soup) -> List[Dict]:
        """Parse events from generic WordPress event layouts."""
        events = []

        # Look for any article/div with event-like structure
        containers = soup.select("article, .event, .event-item, .wp-block-post")
        for el in containers:
            title_el = el.select_one("h2 a, h3 a, h4 a, .entry-title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            source_url = urljoin(self.events_url, title_el.get("href", ""))

            date_el = el.select_one("time, .date, .event-date, .entry-date")
            date_str = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
            event_date, event_time = self._parse_date_text(date_str)

            desc_el = el.select_one("p, .entry-summary, .excerpt")
            description = desc_el.get_text(strip=True) if desc_el else ""

            events.append({
                "title": title,
                "event_date": event_date,
                "event_time": event_time,
                "description": description[:500],
                "location_name": self._name,
                "source_url": source_url,
            })

        return events

    def _parse_date_text(self, text: str) -> tuple:
        if not text:
            return "", ""

        # Try ISO format first
        if re.match(r"\d{4}-\d{2}-\d{2}", text):
            parts = text[:10], ""
            time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)", text[10:])
            if time_match:
                parts = text[:10], time_match.group(1)
            return parts

        # Try common date formats
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(text.strip()[:20], fmt)
                return dt.strftime("%Y-%m-%d"), ""
            except ValueError:
                continue

        # Extract time if present
        time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))", text)
        event_time = time_match.group(1) if time_match else ""

        return text[:30] if len(text) < 50 else "", event_time
