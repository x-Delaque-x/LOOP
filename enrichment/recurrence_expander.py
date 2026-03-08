"""
Recurrence Expander — generates concrete child events from recurring patterns.

For each event with is_recurring=True, creates individual event rows for
the next 4 weeks with specific dates, linked to the parent via parent_event_id.

Idempotent: checks for existing children before creating new ones.
Cleans up past expansions automatically.
"""
import logging
from datetime import date, timedelta

log = logging.getLogger("recurrence_expander")

# Day name -> weekday index (Monday=0)
DAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

WEEKS_AHEAD = 4


def _parse_day_from_pattern(pattern: str) -> int | None:
    """Extract a weekday index from a recurrence pattern like 'Every Saturday'."""
    if not pattern:
        return None
    lower = pattern.lower()
    for day_name, idx in DAYS.items():
        if day_name in lower:
            return idx
    return None


def _next_dates_for_weekday(weekday: int, weeks: int = WEEKS_AHEAD) -> list[date]:
    """Generate the next N occurrences of a given weekday."""
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 0  # Include today if it's that day
    first = today + timedelta(days=days_ahead)
    return [first + timedelta(weeks=w) for w in range(weeks)]


def expand_recurring_events(session):
    """
    Expand recurring events into concrete child instances.

    For each is_recurring=True event with a parseable day pattern,
    creates child events for the next 4 weeks.
    """
    from database_manager import Event

    # Clean up past expanded events
    past_children = session.query(Event).filter(
        Event.parent_event_id.isnot(None),
        Event.event_date_start < date.today(),
    ).all()
    if past_children:
        for child in past_children:
            session.delete(child)
        session.flush()
        log.info(f"Cleaned up {len(past_children)} past expanded events.")

    # Find recurring parents
    parents = session.query(Event).filter(
        Event.is_recurring.is_(True),
        Event.recurrence_pattern.isnot(None),
    ).all()

    if not parents:
        log.info("No recurring events to expand.")
        return

    created = 0
    for parent in parents:
        weekday = _parse_day_from_pattern(parent.recurrence_pattern)
        if weekday is None:
            continue

        dates = _next_dates_for_weekday(weekday)
        for d in dates:
            # Check if child already exists for this date
            existing = session.query(Event).filter_by(
                parent_event_id=parent.id,
                event_date_start=d,
            ).first()
            if existing:
                continue

            child = Event(
                title=parent.title,
                event_date=d.strftime("%Y-%m-%d"),
                event_time=parent.event_time,
                description=parent.description,
                tags=parent.tags,
                source_url=parent.source_url,
                venue_id=parent.venue_id,
                source_id=parent.source_id,
                event_date_start=d,
                event_time_start=parent.event_time_start,
                event_time_end=parent.event_time_end,
                is_recurring=False,
                cost_text=parent.cost_text,
                cost_cents=parent.cost_cents,
                registration_url=parent.registration_url,
                parent_event_id=parent.id,
            )
            session.add(child)
            created += 1

    session.commit()
    log.info(f"Recurring expansion: created {created} child events from {len(parents)} parents.")
