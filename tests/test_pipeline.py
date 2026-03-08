"""Smoke tests for the ETL pipeline components."""
import pytest
from mass_harvest import ADAPTER_MAP, build_adapter, MAX_WORKERS


def test_adapter_map_complete():
    """ADAPTER_MAP covers all known adapter types."""
    expected = {"whofi", "libcal", "recdesk", "wordpress", "drupal"}
    assert set(ADAPTER_MAP.keys()) == expected


def test_max_workers_reasonable():
    """Concurrent worker count is reasonable."""
    assert 1 <= MAX_WORKERS <= 20


def test_config_imports():
    """Config module exports expected constants."""
    from config import APP_NAME, DATABASE_URL, GEMINI_MODEL, MASTER_TAGS, AUDIENCE_TAGS
    assert APP_NAME
    assert DATABASE_URL
    assert GEMINI_MODEL
    assert isinstance(MASTER_TAGS, list) and len(MASTER_TAGS) > 0
    assert isinstance(AUDIENCE_TAGS, list) and len(AUDIENCE_TAGS) > 0


def test_enrichment_imports():
    """Enrichment modules import without error."""
    from enrichment.gemini_tagger import tag_events_batch
    from enrichment.geocoder import geocode_venues
    from enrichment.update_addresses import ADDRESS_MAP
    from enrichment.date_normalizer import normalize_dates, parse_date_text
    from enrichment.cost_parser import parse_cost, cost_from_tags
    assert callable(tag_events_batch)
    assert callable(geocode_venues)
    assert isinstance(ADDRESS_MAP, dict)
    assert callable(normalize_dates)
    assert callable(parse_cost)


def test_cost_parser():
    """Cost parser handles common formats."""
    from enrichment.cost_parser import parse_cost, cost_from_tags

    assert parse_cost("Free") == ("Free", 0)
    assert parse_cost("$5") == ("$5", 500)
    assert parse_cost("$10.50/child") == ("$10.50/child", 1050)
    assert parse_cost("$0") == ("Free", 0)
    assert parse_cost("No charge") == ("Free", 0)
    assert parse_cost("") == (None, None)
    assert parse_cost(None) == (None, None)

    text, cents = parse_cost("Varies")
    assert text == "Varies"
    assert cents is None

    assert cost_from_tags("Arts, Kids (6-12), Free") == ("Free", 0)
    assert cost_from_tags("STEM, Teens (13-17)") == (None, None)
