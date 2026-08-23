import sys
from .gui import *
from .gui_formatting import *
from .gui_modes import *
from .gui_richtext import *
from .gui_state import *
from .gui_theme import *

# Overwrite sys.modules['gui'] to maintain backward compatibility for tests
# that import 'gui' and patch its module-level functions (like get_agent).
from . import gui as _gui_module
sys.modules['gui'] = _gui_module
