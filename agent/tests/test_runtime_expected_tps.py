import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.storage import expected_tokens_per_s


def test_expected_tokens_per_s_tq_override(monkeypatch):
    monkeypatch.setenv("AQUILA_EXPECTED_TOKENS_PER_S", "30")
    monkeypatch.setenv("AQUILA_TQ_EXPECTED_TOKENS_PER_S", "45")
    assert expected_tokens_per_s("stock") == 30.0
    assert expected_tokens_per_s("tq") == 45.0
    assert expected_tokens_per_s(base_url="http://127.0.0.1:11435") == 45.0
