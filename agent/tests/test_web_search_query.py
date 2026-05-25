import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web_search_query import clean_research_query, low_quality_results_note


def test_clean_confirmed_exoplanet_query():
    cleaned, note = clean_research_query("confirmed Earth-like exoplanets NASA")
    assert cleaned.lower().startswith("catalog of")
    assert note is not None


def test_low_quality_dictionary_results_note():
    blob = (
        "Search Results for 'confirmed planets':\n\n"
        "1. Definition\nURL: https://www.dictionary.com/browse/confirm\n"
    )
    msg = low_quality_results_note(blob)
    assert msg is not None
    assert "low-quality" in msg.lower()


def test_trusted_results_no_note():
    blob = (
        "Search Results for 'nasa exoplanet archive':\n\n"
        "URL: https://exoplanetarchive.ipac.caltech.edu/\n"
    )
    assert low_quality_results_note(blob) is None
