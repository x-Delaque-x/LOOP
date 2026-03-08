"""
Drupal/Custom Site Adapter - Extracts events from Drupal and other CMS sites.

Scrapes /events or /calendar pages for event listings.
Works with Drupal Views output, CivicPlus calendars, and generic HTML event pages.
"""
import logging
import re
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from adapters.base_adapter import BaseAdapter

log = logging.getLogger("adapters.drupal")


class DrupalAdapter(BaseAdapter):
    def __init__(self, name: str, website: str, events_url: str = ""):
        self._name = name
        self.website = website
        self.events_url = events_url or website

    @property
    def source_name(self) -> str:
        return self._name

    def fetch_events(self) -> List[Dict]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        # Try event page paths
        urls_to_try = [self.events_url]
        base = self.website.rstrip("/")
        for path in ["/events", "/calendar", "/events/upcoming", "/programs"]:
            candidate = base + path
            if candidate not in urls_to_try:
                urls_to_try.append(candidate)

        for url in urls_to_try:
            events = self._scrape_page(url, headers)
            if events:
                return events

        return []

    def _scrape_page(self, url: str, headers: dict) -> List[Dict]:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.debug(f"Failed to fetch {url}: {e}")
            return []

        events = []

        # Strategy 1: Drupal Views output (common patterns)
        views_rows = soup.select(".views-row, .view-content .node, .view-content article")
        if views_rows:
            for row in views_rows:
                event = self._parse_views_row(row, url)
                if event:
                    events.append(event)
            if events:
                log.info(f"Fetched {len(events)} Drupal Views events from {self._name}")
                return events

        # Strategy 2: CivicPlus calendar entries
        civic_items = soup.select(".calendarList .eventItem, .calendar-list .item, .CivicEventItem")
        if civic_items:
            for item in civic_items:
                event = self._parse_civic_item(item, url)
                if event:
                    events.append(event)
            if events:
                log.info(f"Fetched {len(events)} CivicPlus events from {self._name}")
                return events

        # Strategy 3: Generic article/event patterns
        articles = soup.select("article, .event, .event-item, .program-item, .listing-item")
        for article in articles:
            event = self._parse_article(article, url)
            if event:
                events.append(event)

        if not events:
            # Strategy 4: Any heading + link combo that looks event-like
            for heading in soup.select("h2, h3, h4"):
                link = heading.find("a", href=True)
                if not link:
                    continue
                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                # Skip navigation-style links
                href = link["href"]
                if any(skip in href.lower() for skip in ["login", "contact", "about", "#", "javascript"]):
                    continue

                events.append({
                    "title": title,
                    "event_date": "",
                    "event_time": "",
                    "description": "",
                    "location_name": self._name,
                    "source_url": urljoin(url, href),
                })

        log.info(f"Fetched {len(events)} events from {self._name} (generic scrape)")
        return events

    def _parse_views_row(self, row, page_url: str) -> Dict:
        title_el = row.select_one("h2 a, h3 a, h4 a, .field-name-title a, .views-field-title a")
        if not title_el:
            return {}

        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            return {}

        source_url = urljoin(page_url, title_el.get("href", ""))

        date_el = row.select_one(".date-display-single, .field-name-field-date, time, .views-field-field-date, .event-date")
        date_str = ""
        if date_el:
            date_str = date_el.get("content", "") or date_el.get_text(strip=True)

        event_date, event_time = self._parse_date_text(date_str)

        desc_el = row.select_one(".field-name-body p, .views-field-body, p, .field-type-text-with-summary")
        description = desc_el.get_text(strip=True) if desc_el else ""

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description[:500],
            "location_name": self._name,
            "source_url": source_url,
        }

    def _parse_civic_item(self, item, page_url: str) -> Dict:
        title_el = item.select_one("a, h3, h4, .eventTitle")
        if not title_el:
            return {}

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if not href and title_el.find("a"):
            href = title_el.find("a").get("href", "")

        source_url = urljoin(page_url, href) if href else page_url

        date_el = item.select_one(".eventDate, .date, time")
        date_str = date_el.get_text(strip=True) if date_el else ""
        event_date, event_time = self._parse_date_text(date_str)

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": "",
            "location_name": self._name,
            "source_url": source_url,
        }

    def _parse_article(self, article, page_url: str) -> Dict:
        title_el = article.select_one("h2 a, h3 a, h4 a, .title a")
        if not title_el:
            return {}

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            return {}

        source_url = urljoin(page_url, title_el.get("href", ""))

        date_el = article.select_one("time, .date, .event-date, .field-date")
        date_str = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
        event_date, event_time = self._parse_date_text(date_str)

        desc_el = article.select_one("p, .body, .description, .summary")
        description = desc_el.get_text(strip=True) if desc_el else ""

        return {
            "title": title,
            "event_date": event_date,
            "event_time": event_time,
            "description": description[:500],
            "location_name": self._name,
            "source_url": source_url,
        }

    def _parse_date_text(self, text: str) -> tuple:
        if not text:
            return "", ""

        if re.match(r"\d{4}-\d{2}-\d{2}", text):
            return text[:10], ""

        for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%A, %B %d, %Y"]:
            try:
                dt = datetime.strptime(text.strip()[:30], fmt)
                return dt.strftime("%Y-%m-%d"), ""
            except ValueError:
                continue

        time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))", text)
        event_time = time_match.group(1) if time_match else ""

        return "", event_time
