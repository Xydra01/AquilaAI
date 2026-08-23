import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopEngine


def test_consume_act_stream_aggregates_content():
    def gen():
        yield {"message": {"content": '{"reasoning":"x",'}}
        yield {"message": {"content": '"tools":[]}'}}
        yield {"message": {"thinking": "should not override json"}}

    content, thinking = LoopEngine._consume_act_stream(gen())
    assert '"tools"' in content
    assert thinking == "should not override json"


def test_consume_act_stream_json_from_thinking_when_content_empty():
    def gen():
        yield {
            "message": {
                "thinking": 'plan\n{"reasoning":"ok","tools":[{"name":"web_search","arguments":{"query":"x"}}]}'
            }
        }

    content, _ = LoopEngine._consume_act_stream(gen())
    assert content.startswith("{")
    assert "web_search" in content
