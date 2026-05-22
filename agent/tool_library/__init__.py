from .web_tools import WEB_TOOLS

from .coding_tools import CODING_TOOLS

from .agent_tools import AGENT_TOOLS

from .os_tools import OS_TOOLS

from .email_tools import EMAIL_TOOLS

from .writing_tools import WRITING_TOOLS

from .code_canvas_tools import CODE_CANVAS_TOOLS

from .shell_tools import SHELL_TOOLS

from .grep_tools import GREP_TOOLS

from .git_tools import GIT_TOOLS

from .run_tools import RUN_TOOLS





ALL_TOOLS = {

    **WEB_TOOLS,

    **CODING_TOOLS,

    **AGENT_TOOLS,

    **OS_TOOLS,

    **EMAIL_TOOLS,

    **WRITING_TOOLS,

    **CODE_CANVAS_TOOLS,

    **SHELL_TOOLS,

    **GREP_TOOLS,

    **GIT_TOOLS,

    **RUN_TOOLS,

}

