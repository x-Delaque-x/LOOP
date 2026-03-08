"""Smoke tests for adapter imports and instantiation."""
import pytest
from adapters.base_adapter import BaseAdapter
from adapters.whofi_adapter import WhoFiAdapter
from adapters.libcal_adapter import LibCalAdapter
from adapters.recdesk_adapter import RecDeskAdapter
from adapters.wordpress_adapter import WordPressAdapter
from adapters.drupal_adapter import DrupalAdapter


def test_base_adapter_is_abstract():
    """BaseAdapter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseAdapter()


def test_whofi_adapter_instantiation():
    adapter = WhoFiAdapter(name="Test Library", website="https://example.com",
                           events_url="https://example.com/events", api_endpoint="")
    assert adapter.source_name == "Test Library"
    assert hasattr(adapter, "fetch_events")


def test_libcal_adapter_instantiation():
    adapter = LibCalAdapter(name="Test Library", website="https://example.com",
                            events_url="https://example.com/events",
                            api_endpoint="", cal_id="12345")
    assert adapter.source_name == "Test Library"
    assert adapter.cal_id == "12345"


def test_recdesk_adapter_instantiation():
    adapter = RecDeskAdapter(name="Test Rec", website="https://example.recdesk.com",
                             events_url="https://example.recdesk.com/events")
    assert adapter.source_name == "Test Rec"


def test_wordpress_adapter_instantiation():
    adapter = WordPressAdapter(name="Test WP", website="https://example.com",
                               events_url="https://example.com/events")
    assert adapter.source_name == "Test WP"


def test_drupal_adapter_instantiation():
    adapter = DrupalAdapter(name="Test Drupal", website="https://example.com",
                            events_url="https://example.com/events")
    assert adapter.source_name == "Test Drupal"


def test_all_adapters_have_fetch_events():
    """Every adapter implements fetch_events."""
    adapters = [
        WhoFiAdapter(name="t", website="u", events_url="u", api_endpoint=""),
        LibCalAdapter(name="t", website="u", events_url="u"),
        RecDeskAdapter(name="t", website="u", events_url="u"),
        WordPressAdapter(name="t", website="u", events_url="u"),
        DrupalAdapter(name="t", website="u", events_url="u"),
    ]
    for adapter in adapters:
        assert callable(getattr(adapter, "fetch_events", None))
