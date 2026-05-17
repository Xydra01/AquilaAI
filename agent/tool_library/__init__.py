from .web_tools import WEB_TOOLS
from .coding_tools import CODING_TOOLS
from .agent_tools import AGENT_TOOLS
from .os_tools import OS_TOOLS
from .email_tools import EMAIL_TOOLS
from .writing_tools import WRITING_TOOLS
from .code_canvas_tools import CODE_CANVAS_TOOLS


ALL_TOOLS = {
    **WEB_TOOLS,
    **CODING_TOOLS,
    **AGENT_TOOLS,
    **OS_TOOLS,
    **EMAIL_TOOLS,
    **WRITING_TOOLS,
    **CODE_CANVAS_TOOLS,
}