"""Tests for Chat Mode light research planning."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.research.light_research_plan import (
    derive_light_search_queries,
    extract_urls_from_text,
    plan_light_research,
)


def test_extract_urls_markdown_link():
    text = "See [article](https://news.example.com/story) for details."
    assert extract_urls_from_text(text) == ["https://news.example.com/story"]


def test_derive_query_from_long_prompt_with_question():
    prompt = (
        "I've been reading about the Mongol Empire for a class project. "
        "There's a lot about Genghis Khan and Kublai Khan and trade routes. "
        "What caused the Mongol Empire to fragment after Kublai Khan died?"
    )
    queries = derive_light_search_queries(prompt, max_queries=1, max_words=18)
    assert queries
    assert "fragment" in queries[0].lower() or "kublai" in queries[0].lower()
    assert len(queries[0].split()) <= 18


def test_plan_skips_search_for_link_only_message():
    plan = plan_light_research("Please summarize https://example.com/report.pdf")
    assert plan.skip_search is True
    assert plan.user_urls == ("https://example.com/report.pdf",)
    assert plan.search_queries == ()


def test_plan_search_and_urls_for_mixed_message():
    plan = plan_light_research(
        "Read https://example.com/a and also what is Pax Mongolica?"
    )
    assert plan.user_urls
    assert not plan.skip_search
    assert plan.search_queries


def test_derive_two_queries_for_two_questions():
    text = "Who was Genghis Khan? Also what was the Pax Mongolica?"
    queries = derive_light_search_queries(text, max_queries=2, max_words=14)
    assert len(queries) == 2


def test_weather_query_avoids_dictionary_bait():
    q = derive_light_search_queries(
        "What does the weather look like this week in Warwick, RI?",
        max_queries=2,
        max_words=18,
    )
    assert q
    joined = " ".join(q).lower()
    assert "weather" in joined or "forecast" in joined
    assert "warwick" in joined
    # Should not collapse to a single throwaway word like "try"
    assert all(len(x.split()) >= 2 for x in q)
