import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from instance_registry import create_instance, ensure_default_instance
from persona_registry import create_persona, get_persona
from tool_library.persona_tools import (
    INIT_DOC_MIN_CHARS,
    clear_active_persona_build,
    finalize_persona,
    set_active_persona_build,
    write_persona_file,
)


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    ensure_default_instance()
    yield
    clear_active_persona_build()


def test_write_and_finalize_scoped_to_persona_dir():
    inst = create_instance("Tools", default_mode="character")
    p = create_persona(inst.id, "Elena", build_complete=False)
    set_active_persona_build(inst.id, p.id)
    short = write_persona_file("initialization.md", "too short")
    assert "❌" in short
    body = "x" * INIT_DOC_MIN_CHARS
    bad = write_persona_file(
        "rp/persona_build_horror/initialization.md",
        body,
    )
    assert "❌" in bad
    assert "initialization.md" in bad
    abs_path = write_persona_file(
        "F:/tmp/persona_build_horror/initialization.md",
        body,
    )
    assert "❌" in abs_path
    escape = write_persona_file("../escape.md", "nope")
    assert "❌" in escape
    ok = write_persona_file("initialization.md", body)
    assert "✅" in ok
    assert f"personas/{p.id}/initialization.md" in ok.replace("\\", "/")
    dup = write_persona_file("initialization.md", body)
    assert "OS BLOCK" in dup
    fin = finalize_persona("Ahoy!", tagline="Sailor")
    assert "✅" in fin
    updated = get_persona(inst.id, p.id)
    assert updated.build_complete
    assert updated.greeting == "Ahoy!"
