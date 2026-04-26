import sys
from pathlib import Path

# Ensures Python can see your root directory regardless of how you run the script
sys.path.append(str(Path(__file__).parent.resolve()))

from tool_library import ALL_TOOLS

def print_arsenal():
    print("=== 🦅 AQUILA OS: EXTENDED TOOL LIBRARY ===")
    print(f"Total Tools Loaded: {len(ALL_TOOLS)}\n")

    for tool_name, tool_info in ALL_TOOLS.items():
        print(f"🛠️ Tool: {tool_name}")
        
        # Grab the description, handling cases where it might be missing
        description = tool_info.get("description")
        if not description:
            description = "No description provided."
            
        print(f"📝 Description: {description.strip()}")
        print("-" * 50)

if __name__ == "__main__":
    print_arsenal()