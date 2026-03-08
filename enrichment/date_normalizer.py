"""
Date Normalizer — parses freeform event_date/event_time strings into
structured Date/Time columns for sorting and filtering.

Runs as a post-harvest enrichment step. Never modifies the original
event_date text (upsert natural key depends on it).
"""
import re
import logging
from datetime import datetime, date, time

log = logging.getLogger("date_normalizer")

# Days of the week for recurring pattern detection
DAYS_OF_WEEK = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Regex for recurring patterns
RE_EVERY_DAY = re.compile(
    r"^every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    re.IGNORECASE,
)
RE_RECURRING = re.compile(
    r"^(every|weekly|biweekly|monthly|ongoing|repeats)",
    re.IGNORECASE,
)

# Ordinal suffix removal: 1st, 2nd, 3rd, 4th, ...
RE_ORDINAL = re.compile(r"(\d+)(st|nd|rd|th)\b")

# Date parse formats to try, in order
DATE_FORMATS = [
    "%Y-%m-%d",          # 2025-03-15
    "%B %d, %Y",         # March 15, 2025
    "%b %d, %Y",         # Mar 15, 2025
    "%m/%d/%Y",          # 03/15/2025
    "%m/%d/%y",          # 03/15/25
    "%B %d %Y",          # March 15 2025
    "%b %d %Y",          # Mar 15 2025
    "%B %d",             # March 15 (infer current/next year)
    "%b %d",             # Mar 15 (infer current/next year)
    "%d %B",             # 15 March (infer year)
    "%d %b",             # 15 Mar (infer year)
    "%b %d, %Y %I:%M%p", # Mar 9, 2026 5:30pm (date with embedded time)
    "%b %d, %Y %I:%M %p", # Mar 9, 2026 5:30 PM
]

# Time parse formats
TIME_FORMATS = [
    "%I:%M %p",          # 2:00 PM
    "%I:%M%p",           # 2:00PM
    "%I %p",             # 2 PM
    "%H:%M",             # 14:00
]


def _strip_day_prefix(text: str) -> str:
    """Remove leading day name: 'Saturday, March 15' -> 'March 15'."""
    for day in DAYS_OF_WEEK:
        pattern = re.compile(rf"^{day}\s*,?\s*", re.IGNORECASE)
        text = pattern.sub("", text)
    return text.strip()


def _strip_ordinals(text: str) -> str:
    """Remove ordinal suffixes: '15th' -> '15'."""
    return RE_ORDINAL.sub(r"\1", text)


def parse_date_text(text: str) -> tuple:
    """
    Parse freeform date text into (date|None, is_recurring, recurrence_pattern|None).

    Returns:
        (parsed_date, is_recurring, recurrence_pattern)
    """
    if not text or not text.strip():
        return None, False, None

    text = text.strip()

    # Check for recurring patterns first
    if RE_RECURRING.match(text):
        return None, True, text

    # Check for TBD / unknown
    if text.lower() in ("tbd", "tba", "unknown", "n/a", "varies"):
        return None, False, None

    # Clean the text
    cleaned = _strip_day_prefix(text)
    cleaned = _strip_ordinals(cleaned)

    # Try each format
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            # For formats without year, infer current or next year
            if "%Y" not in fmt and "%y" not in fmt:
                today = date.today()
                parsed = parsed.replace(year=today.year)
                if parsed.date() < today:
                    parsed = parsed.replace(year=today.year + 1)
            return parsed.date(), False, None
        except ValueError:
            continue

    # Last resort: look for a date embedded in longer text
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date(), False, None
        except ValueError:
            pass

    log.debug(f"Could not parse date: '{text}'")
    return None, False, None


def parse_time_text(text: str) -> tuple:
    """
    Parse freeform time text into (start_time, end_time).

    Handles formats like:
    - "2:00 PM"
    - "10:00 AM - 2:00 PM"
    - "10:00am-2:00pm"

    Returns:
        (start_time|None, end_time|None)
    """
    if not text or not text.strip():
        return None, None

    text = text.strip()

    # Split on common range separators
    parts = re.split(r"\s*[-–—to]+\s*", text, maxsplit=1)

    start = _parse_single_time(parts[0].strip())
    end = _parse_single_time(parts[1].strip()) if len(parts) > 1 else None

    return start, end


def _parse_single_time(text: str) -> time | None:
    """Parse a single time string."""
    if not text:
        return None

    text = text.strip().upper().replace(".", "")

    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue

    return None


def normalize_dates(session):
    """
    Normalize all event dates/times in the database.
    Only processes events where event_date_start is NULL.
    """
    from database_manager import Event

    events = session.query(Event).filter(
        Event.event_date_start.is_(None),
        Event.event_date.isnot(None),
        Event.event_date != "",
    ).all()

    if not events:
        log.info("No events need date normalization.")
        return

    parsed_count = 0
    recurring_count = 0

    for event in events:
        parsed_date, is_recurring, pattern = parse_date_text(event.event_date)

        if parsed_date:
            event.event_date_start = parsed_date
            parsed_count += 1
        if is_recurring:
            event.is_recurring = True
            event.recurrence_pattern = pattern
            recurring_count += 1

        # Parse time if we haven't yet
        if event.event_time_start is None and event.event_time:
            start_time, end_time = parse_time_text(event.event_time)
            if start_time:
                event.event_time_start = start_time
            if end_time:
                event.event_time_end = end_time

    session.commit()
    log.info(f"Date normalization: {parsed_count} dates parsed, {recurring_count} recurring detected "
             f"(out of {len(events)} processed)")
