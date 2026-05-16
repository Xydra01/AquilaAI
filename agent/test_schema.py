import json
import inspect

# Import your tools
from tools import SURVIVAL_TOOLS
try:
    from tool_library import ALL_TOOLS
except ImportError:
    ALL_TOOLS = {}

def build_strict_schema(available_tools: dict) -> dict:
    tool_schemas = []
    valid_tool_names = list(available_tools.keys()) # Grab the exact names
    
    for name, meta in available_tools.items():
        func = meta["func"]
        sig = inspect.signature(func)
        
        props = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param.kind in [inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL]:
                continue
            props[param_name] = {"type": "string"}
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
                
        tool_schemas.append({
            "type": "object",
            "properties": {
                "name": {"const": name},
                "arguments": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                    "additionalProperties": True
                }
            },
            "required": ["name", "arguments"]
        })

    return {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "final_report": {"type": "string"},
            "tools": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": valid_tool_names # <-- THE IRONCLAD LOCK
                        }
                    },
                    "anyOf": tool_schemas
                }
            }
        },
        "required": ["reasoning", "tools"],
        "additionalProperties": False
    }

if __name__ == "__main__":
    executable_tools = {**SURVIVAL_TOOLS, **ALL_TOOLS}
    
    schema = build_strict_schema(executable_tools)
    
    with open("schema_dump.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4)
        
    print("✅ Schema generated! Open 'schema_dump.json' to view the strict constraints.")
    print(f"🔒 Locked Tool Names: {list(executable_tools.keys())}")