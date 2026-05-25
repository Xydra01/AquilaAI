"""Tests for paywall / thin-page heuristics."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web_content_quality import analyze_fetched_page, format_tool_result_for_quality

SPRINGER_PREVIEW = """
# Emerging Trends and Future Research Directions in Plankton Studies
## Abstract
The study and monitoring of plankton are essential for understanding marine ecosystems.
This is a preview of subscription content, log in via an institution to check access.
## Access this chapter
Log in via an institution
## Subscribe and save
Springer+ from $39.99 /Month
## Buy Now
eBook: USD 18.99
Buy eBook
Softcover Book: USD 18.99
Buy Softcover Book
"""

NOAA_BODY = """
# Plankton | Definition, Characteristics, Types
Plankton are organisms that drift in water and cannot swim against currents.
Marine plankton includes protists, microanimals, bacteria, and viruses.
Researchers use plankton nets and imaging systems to monitor abundance over decades.
NOAA Fisheries maintains long-running monitoring programs with public data portals.
""" * 3


def test_springer_preview_classified_paywall():
    analysis = analyze_fetched_page(
        "https://link.springer.com/chapter/10.1007/978-3-031-76121-8_34",
        SPRINGER_PREVIEW,
    )
    assert analysis.quality == "paywall"
    assert analysis.paywall_score >= 5
    formatted = format_tool_result_for_quality(
        "https://link.springer.com/chapter/10.1007/978-3-031-76121-8_34",
        f"Content of url:\n\n{SPRINGER_PREVIEW}",
        analysis,
    )
    assert "OS Note" in formatted
    assert "paywall" in formatted.lower()
    assert len(formatted) < len(SPRINGER_PREVIEW) * 2


def test_noaa_like_page_classified_full():
    analysis = analyze_fetched_page(
        "https://oceanservice.noaa.gov/facts/plankton.html",
        NOAA_BODY,
    )
    assert analysis.quality == "full"
    assert analysis.is_usable_for_context()


def test_error_markdown():
    analysis = analyze_fetched_page("https://example.com", "❌ Error reading URL: timeout")
    assert analysis.quality == "error"
    assert not analysis.is_usable_for_context()


def test_empty_content():
    analysis = analyze_fetched_page("https://example.com", "   ")
    assert analysis.quality == "error"
