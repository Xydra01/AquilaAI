"""Aquila Remote Companion server package.

Wraps the existing headless Aquila brain (``get_agent`` + streaming
``OllamaClient``) in a FastAPI app so phones and laptops can talk to the host
over a private Tailscale network via an installable PWA.

The rest of the codebase imports sibling modules by bare name (``import main``)
with the ``agent/`` directory on ``sys.path``. To keep that contract working no
matter how the server is launched (``python -m uvicorn``, console script, or a
test harness), make sure the parent ``agent/`` directory is importable.
"""
from __future__ import annotations

import os
import sys

_AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

__all__ = ["_AGENT_DIR"]
