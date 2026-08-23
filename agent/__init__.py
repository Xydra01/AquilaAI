import sys
from pathlib import Path

# Add subdirectories to sys.path to maintain backwards compatibility
# while we progressively update imports across the codebase.
_agent_dir = Path(__file__).parent.resolve()
_agent_dir_str = str(_agent_dir)
if _agent_dir_str not in sys.path:
    sys.path.append(_agent_dir_str)
for _sub in ("storage", "parser", "policies", "research", "coding", "gui", "core"):
    _sub_path = str(_agent_dir / _sub)
    if _sub_path not in sys.path:
        sys.path.append(_sub_path)
# Alias main module to agent.core.main to support legacy test imports
# while ensuring absolute/relative package import resolution works.
import agent.core.main
sys.modules['main'] = agent.core.main
sys.modules['agent.main'] = agent.core.main
sys.modules['core'] = sys.modules['agent.core']

import agent.core.generation_lock
sys.modules['generation_lock'] = agent.core.generation_lock
sys.modules['agent.generation_lock'] = agent.core.generation_lock
import agent.core.mcp_host
sys.modules['mcp_host'] = agent.core.mcp_host
sys.modules['agent.mcp_host'] = agent.core.mcp_host
import agent.research.search_config
sys.modules['search_config'] = agent.research.search_config
sys.modules['agent.search_config'] = agent.research.search_config

# Storage aliases
import agent.storage.workspace_paths
sys.modules['workspace_paths'] = agent.storage.workspace_paths
sys.modules['agent.workspace_paths'] = agent.storage.workspace_paths
import agent.storage.instance_runtime
sys.modules['instance_runtime'] = agent.storage.instance_runtime
sys.modules['agent.instance_runtime'] = agent.storage.instance_runtime
import agent.storage.runtime_settings
sys.modules['runtime_settings'] = agent.storage.runtime_settings
sys.modules['agent.runtime_settings'] = agent.storage.runtime_settings
import agent.storage.learn_registry
sys.modules['learn_registry'] = agent.storage.learn_registry
sys.modules['agent.learn_registry'] = agent.storage.learn_registry
import agent.storage.persona_registry
sys.modules['persona_registry'] = agent.storage.persona_registry
sys.modules['agent.persona_registry'] = agent.storage.persona_registry
import agent.storage.memory_singleton
sys.modules['memory_singleton'] = agent.storage.memory_singleton
sys.modules['agent.memory_singleton'] = agent.storage.memory_singleton

# Parser aliases
import agent.parser.stream_output_guard
sys.modules['stream_output_guard'] = agent.parser.stream_output_guard
sys.modules['agent.stream_output_guard'] = agent.parser.stream_output_guard
import agent.parser.structured_parse
sys.modules['structured_parse'] = agent.parser.structured_parse
sys.modules['agent.structured_parse'] = agent.parser.structured_parse
import agent.parser.ollama_messages
sys.modules['ollama_messages'] = agent.parser.ollama_messages
sys.modules['agent.ollama_messages'] = agent.parser.ollama_messages
import agent.parser.structured_schema
sys.modules['structured_schema'] = agent.parser.structured_schema
sys.modules['agent.structured_schema'] = agent.parser.structured_schema

# Coding aliases
import agent.coding.file_parser
sys.modules['file_parser'] = agent.coding.file_parser
sys.modules['agent.file_parser'] = agent.coding.file_parser
import agent.coding.language_registry
sys.modules['language_registry'] = agent.coding.language_registry
sys.modules['agent.language_registry'] = agent.coding.language_registry

# Core aliases
import agent.core.loop_engine
sys.modules['loop_engine'] = agent.core.loop_engine
sys.modules['agent.loop_engine'] = agent.core.loop_engine
import agent.core.explore_agent
sys.modules['explore_agent'] = agent.core.explore_agent
sys.modules['agent.explore_agent'] = agent.core.explore_agent
import agent.core.prompts
sys.modules['prompts'] = agent.core.prompts
sys.modules['agent.prompts'] = agent.core.prompts

# Policies / tool_catalog aliases
import agent.policies.tool_catalog
sys.modules['tool_catalog'] = agent.policies.tool_catalog
sys.modules['agent.tool_catalog'] = agent.policies.tool_catalog

# Export as attributes to support 'from agent import name'
main = agent.core.main
core = agent.core
generation_lock = agent.core.generation_lock
mcp_host = agent.core.mcp_host
search_config = agent.research.search_config
workspace_paths = agent.storage.workspace_paths
instance_runtime = agent.storage.instance_runtime
runtime_settings = agent.storage.runtime_settings
learn_registry = agent.storage.learn_registry
persona_registry = agent.storage.persona_registry
memory_singleton = agent.storage.memory_singleton
stream_output_guard = agent.parser.stream_output_guard
structured_parse = agent.parser.structured_parse
ollama_messages = agent.parser.ollama_messages
structured_schema = agent.parser.structured_schema
file_parser = agent.coding.file_parser
language_registry = agent.coding.language_registry
loop_engine = agent.core.loop_engine
explore_agent = agent.core.explore_agent
prompts = agent.core.prompts

