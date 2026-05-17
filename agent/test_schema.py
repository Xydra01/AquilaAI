import json
import inspect

from tools import SURVIVAL_TOOLS

try:
    from tool_library import ALL_TOOLS
except ImportError:
    ALL_TOOLS = {}

from main import build_strict_schema, get_executable_tools, validate_tool_calls

if __name__ == "__main__":
    executable_tools = get_executable_tools()
    schema = build_strict_schema(executable_tools)

    with open("schema_dump.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4)

    print("Schema generated: schema_dump.json")
    print(f"Locked tool names ({len(executable_tools)}): {list(executable_tools.keys())[:5]}...")

    ok, err = validate_tool_calls([
        {"tool_name": "read_file", "arguments": {"file_path": "x"}},
    ])
    print(f"validate_tool_calls rejects tool_name: ok={ok}, err={err}")
