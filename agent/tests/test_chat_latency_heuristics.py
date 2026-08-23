import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core.main import _chat_recall_n_results


def test_chat_recall_skips_short_followups():
    assert _chat_recall_n_results("ok") == 0
    assert _chat_recall_n_results("why?") == 0
    assert _chat_recall_n_results("thanks, continue") == 0


def test_chat_recall_keeps_context_for_real_question():
    assert _chat_recall_n_results("Can you compare Redis and SQLite for caching?") == 2
