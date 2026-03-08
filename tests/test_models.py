"""Smoke tests for database models and relationships."""
import pytest
from database_manager import (
    Base, Municipality, Source, Venue, Event, URLSubmission,
    GoldenEvent, SessionLocal, init_db,
)


def test_all_models_importable():
    """All model classes import without error."""
    assert Municipality.__tablename__ == "municipalities"
    assert Source.__tablename__ == "sources"
    assert Venue.__tablename__ == "venues"
    assert Event.__tablename__ == "events"
    assert URLSubmission.__tablename__ == "url_submissions"


def test_golden_event_alias():
    """GoldenEvent is an alias for Event (backward compat)."""
    assert GoldenEvent is Event


def test_municipality_columns():
    """Municipality has expected columns."""
    cols = {c.name for c in Municipality.__table__.columns}
    assert {"id", "name", "county", "population", "has_library", "has_recreation",
            "library_status", "recreation_status"} <= cols


def test_source_has_municipality_fk():
    """Source model has municipality_id foreign key."""
    cols = {c.name for c in Source.__table__.columns}
    assert "municipality_id" in cols


def test_source_relationship():
    """Source has municipality relationship defined."""
    assert hasattr(Source, "municipality")
    assert hasattr(Source, "venues")
    assert hasattr(Source, "events")


def test_event_relationships():
    """Event has venue and source relationships."""
    assert hasattr(Event, "venue")
    assert hasattr(Event, "source")


def test_url_submission_columns():
    """URLSubmission has expected columns."""
    cols = {c.name for c in URLSubmission.__table__.columns}
    assert {"id", "municipality_id", "url", "source_type", "submitter_note",
            "status", "created_at"} <= cols


def test_session_local_callable():
    """SessionLocal is callable (creates sessions)."""
    assert callable(SessionLocal)


def test_init_db_callable():
    """init_db function exists and is callable."""
    assert callable(init_db)
