from explore_agent import ExplorationBrief, _brief_from_findings


def test_brief_from_findings_extracts_paths():
    brief = _brief_from_findings(
        ["read_code_outline ok", "found agent/main.py"],
        "implement feature",
    )
    assert isinstance(brief, ExplorationBrief)
    assert brief.to_markdown()
    assert brief.suggested_plan_sketch
