import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import AQUILA_ACTION_SCHEMA, get_executable_tools


def test_schema_built_from_filtered_tools():
    tools = get_executable_tools()
    schema_tools = AQUILA_ACTION_SCHEMA["properties"]["tools"]["items"]["anyOf"]
    schema_names = {item["properties"]["name"]["const"] for item in schema_tools}
    assert schema_names == set(tools.keys())
    assert "_index_codebase" not in schema_names
