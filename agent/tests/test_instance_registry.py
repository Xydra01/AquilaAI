import json
from pathlib import Path

import pytest

from agent.storage import (
    create_instance,
    delete_instance,
    ensure_default_instance,
    get_active_instance_id,
    get_instance,
    list_instances,
    set_active_instance_id,
    workspace_summary_path,
)


@pytest.fixture(autouse=True)
def isolated_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    (tmp_path / "Agent-Instances").mkdir(parents=True, exist_ok=True)
    yield


def test_ensure_default_instance():
    inst = ensure_default_instance()
    assert inst.id == "default"


def test_create_and_list_instances():
    a = create_instance("Research Bot", specialty="papers", default_mode="research")
    b = create_instance("Coder", default_mode="code")
    names = {i.id for i in list_instances()}
    assert a.id in names
    assert b.id in names


def test_active_instance_roundtrip():
    inst = create_instance("Switcher")
    set_active_instance_id(inst.id)
    assert get_active_instance_id() == inst.id


def test_workspace_summary_path_exists_after_create():
    inst = create_instance("Writer", default_mode="writing")
    path = workspace_summary_path(inst.id)
    assert path.is_file()
    assert "Workspace summary" in path.read_text(encoding="utf-8")


def test_delete_instance_removes_data_and_switches_active():
    inst = create_instance("Disposable")
    set_active_instance_id(inst.id)
    assert get_instance(inst.id) is not None
    delete_instance(inst.id)
    assert get_instance(inst.id) is None
    assert get_active_instance_id() == "default"
    assert not workspace_summary_path(inst.id).exists()


def test_delete_default_instance_raises():
    ensure_default_instance()
    with pytest.raises(ValueError, match="default"):
        delete_instance("default")
