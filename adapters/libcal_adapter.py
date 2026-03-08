"""
LibCal Adapter - Extracts events from libraries using the Springshare LibCal platform.

LibCal exposes event data via: /ajax/calendar/list/?c={cal_id}&date={YYYY-MM-DD}
This returns JSON with full event details including title, description, dates, location.

The adapter fetches events in weekly intervals (~5 requests instead of 30) with dedup.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
from adapters.base_adapter import BaseAdapter

log = logging.getLogger("adapters.libcal")


class LibCalAdapter(BaseAdapter):
    def __init__(self, name: str, website: str, events_url: str = "",
                 api_endpoint: str = "", cal_id: str = ""):
        self._name = name
        self.website = website
        self.events_url = events_url or website
        self.api_endpoint = api_endpoint
        self.cal_id = cal_id

    @property
    def source_name(self) -> str:
        return self._name

    def fetch_events(self) -> List[Dict]:
        headers = {
            "User-Agent": "LOOP/1.0 (Family Events Aggregator)",
            "X-Requested-With": "XMLHttpRequest",
        }

        # Strategy 1: Use the AJAX calendar list endpoint (most reliable)
        if self.cal_id:
            events = self._fetch_ajax_calendar(self.cal_id, headers)
            if events:
                return events

        # Strategy 2: Auto-discover cal_id from the LibCal page
        discovered_cid = self._discover_cal_id(headers)
        if discovered_cid:
            events = self._fetch_ajax_calendar(discovered_cid, headers)
            if events:
                return events

        # Strategy 3: Scrape event links from the HTML page
        events = self._scrape_events_page(headers)
        return events

    def _discover_cal_id(self, headers: dict) -> str:
        """Try to discover the main calendar ID from the LibCal site."""
        import re

        # Determine the LibCal base URL
        base = self._get_libcal_base()
        if not base:
            return ""

        try:
            for page_path in ["/calendar", ""]:
                resp = requests.get(base + page_path, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                # Find calendarId in the page source
                cids = set()
                for m in re.finditer(r'(?:calendarId|cal_id)\s*[=:\"\']+\s*[\"\']*(\d{3,})', resp.text):
                    cids.add(m.group(1))

                # Test each candidate to find one that returns events
                for cid in cids:
                    test_url = f"{base}/ajax/calendar/list/?c={cid}&date={datetime.now().strftime('%Y-%m-%d')}"
                    try:
                        r = requests.get(test_url, headers=headers, timeout=10)
                        data = r.json()
                        if data.get("total_results", 0) > 0:
                            log.info(f"Discovered working cal_id={cid} for {self._name}")
                            return cid
                    except Exception:
                        continue

                # If none had events today, try the first one found
                if cids:
                    return sorted(cids)[0]

        except Exception as e:
            log.debug(f"Cal ID discovery failed for {self._name}: {e}")

        return ""

    def _get_libcal_base(self) -> str:
        """Determine the LibCal subdomain base URL."""
        # If events_url is already a libcal.com URL, use it
        if "libcal.com" in self.events_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.events_url)
            return f"{parsed.scheme}://{parsed.netloc}"

        # Try to find LibCal URL by checking the website
        try:
            resp = requests.get(self.website, timeout=10,
                                headers={"User-Agent": "LOOP/1.0"})
            import re
            m = re.search(r'(https?://\w+\.libcal\.com)', resp.text)
            if m:
                return m.group(1)
        except Exception:
            pass

        return ""

    def _fetch_ajax_calendar(self, cal_id: str, headers: dict) -> List[Dict]:
        """Fetch events using the LibCal AJAX calendar list endpoint.

        Uses weekly intervals (every 7 days) instead of daily requests,
        reducing API calls from ~30 to ~5 per source.
        """
        base = self._get_libcal_base()
        if not base:
            log.warning(f"No LibCal base URL found for {self._name}")
            return []

        events = []
        seen_ids = set()
        today = datetime.now()

        # Fetch in weekly intervals — LibCal returns the full week of events
        for week_offset in range(5):  # 5 weeks ≈ 35 days of coverage
            date = today + timedelta(weeks=week_offset)
            date_str = date.strftime("%Y-%m-%d")
            url = f"{base}/ajax/calendar/list/?c={cal_id}&date={date_str}"

            try:
                resp = requests.get(url, headers=headers, timeout=10)
                data = resp.json()

                for item in data.get("results", []):
                    event_id = item.get("id")
                    if event_id in seen_ids:
                        continue
                    seen_ids.add(event_id)

                    event = self._parse_ajax_event(item)
                    if event:
                        events.append(event)

            except Exception as e:
                log.debug(f"Failed to fetch {self._name} for {date_str}: {e}")
                continue

        log.info(f"Fetched {len(events)} events from {self._name} (LibCal AJAX, 5 weekly requests)")
        return events

    def _parse_ajax_event(self, item: dict) -> Dict:
        """Parse an event from the LibCal AJAX calendar list response."""
        title = item.get("title", "").strip()
        if not title:
            return {}

        # Parse dates from the structured fields
        event_date = ""
        event_time = ""

        startdt = item.get("startdt", "")
        if startdt:
            try:
                dt = datetime.strptime(startdt, "%Y-%m-%d %H:%M:%S")
                event_date = dt.strftime("%Y-%m-%d")
                event_time = dt.strftime("%I:%M %p")
            except ValueError:
                event_date = startdt
        elif item.get("date"):
            event_date = item["date"]

        # Description — strip HTML
        description = item.get("description", "") or item.get("shortdesc", "")
        if description and "<" in description:
            description = BeautifulSoup(description, "html.parser").get_text(strip=True)

        # URL
        source_url = item.get("url", "") or self.website

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description.strip(),
            "location_name": self._name,
            "source_url": str(source_url).strip(),
        }

    def _scrape_events_page(self, headers: dict) -> List[Dict]:
        """Scrape events from the HTML page as a last-resort fallback."""
        try:
            resp = requests.get(self.events_url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.error(f"Failed to scrape {self._name}: {e}")
            return []

        events = []
        event_elements = (
            soup.select(".s-lc-ea-event") or
            soup.select(".event-list-item") or
            soup.select(".s-lib-public-event") or
            soup.select("[class*='event']")
        )

        for el in event_elements:
            title_el = el.select_one("h3, h4, .event-title, .s-lc-ea-ttl, a[class*='title']")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.find("a")
            from urllib.parse import urljoin
            source_url = urljoin(self.events_url, link["href"]) if link and link.get("href") else self.events_url

            date_el = el.select_one(".event-date, .s-lc-ea-sdt, time, [class*='date']")
            date_str = date_el.get_text(strip=True) if date_el else ""

            desc_el = el.select_one(".event-description, .s-lc-ea-desc, p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            events.append({
                "title": title,
                "event_date": date_str,
                "event_time": "",
                "description": description,
                "location_name": self._name,
                "source_url": source_url,
            })

        log.info(f"Scraped {len(events)} events from {self._name} HTML")
        return events
