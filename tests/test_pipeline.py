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
    from config import APP_NAME, DATABASE_URL, GEMINI_MODEL, MASTER_TAGS, AGE_TAGS
    assert APP_NAME
    assert DATABASE_URL
    assert GEMINI_MODEL
    assert isinstance(MASTER_TAGS, list) and len(MASTER_TAGS) > 0
    assert isinstance(AGE_TAGS, list) and len(AGE_TAGS) > 0


def test_enrichment_imports():
    """Enrichment modules import without error."""
    from enrichment.gemini_tagger import tag_events_batch
    from enrichment.geocoder import geocode_venues
    from enrichment.update_addresses import ADDRESS_MAP
    assert callable(tag_events_batch)
    assert callable(geocode_venues)
    assert isinstance(ADDRESS_MAP, dict)
