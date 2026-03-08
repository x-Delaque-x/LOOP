"""Tests for the municipality registry."""
import pytest
from scout.ri_municipalities import RI_MUNICIPALITIES


def test_exactly_39_municipalities():
    """Rhode Island has exactly 39 municipalities."""
    assert len(RI_MUNICIPALITIES) == 39


def test_no_duplicate_names():
    """All municipality names are unique."""
    names = [m["name"] for m in RI_MUNICIPALITIES]
    assert len(names) == len(set(names))


def test_required_fields():
    """Every municipality has all required fields."""
    required = {"name", "county", "population", "has_library", "has_recreation"}
    for muni in RI_MUNICIPALITIES:
        missing = required - set(muni.keys())
        assert not missing, f"{muni['name']} missing fields: {missing}"


def test_valid_counties():
    """All counties are valid RI counties."""
    valid_counties = {"Bristol", "Kent", "Newport", "Providence", "Washington"}
    for muni in RI_MUNICIPALITIES:
        assert muni["county"] in valid_counties, f"{muni['name']} has invalid county: {muni['county']}"


def test_populations_positive():
    """All populations are positive integers."""
    for muni in RI_MUNICIPALITIES:
        assert isinstance(muni["population"], int) and muni["population"] > 0, \
            f"{muni['name']} has invalid population: {muni['population']}"


def test_known_municipalities_present():
    """Key municipalities are in the registry."""
    names = {m["name"] for m in RI_MUNICIPALITIES}
    expected = {"Providence", "Warwick", "Cranston", "Pawtucket", "North Kingstown",
                "South Kingstown", "East Greenwich", "Westerly", "Newport", "Bristol"}
    assert expected <= names


def test_alphabetical_order():
    """Municipalities are listed in alphabetical order."""
    names = [m["name"] for m in RI_MUNICIPALITIES]
    assert names == sorted(names)
