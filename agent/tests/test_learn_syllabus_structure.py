"""Syllabus depth validation gates."""
from learn_registry import SYLLABUS_MIN_CHILD_NODES, SYLLABUS_MIN_NODES, validate_syllabus_structure


def _nodes(n: int, children: int) -> list[dict]:
    out = [{"id": "root", "title": "Overview", "parent_id": None}]
    for i in range(children):
        out.append(
            {
                "id": f"c{i}",
                "title": f"Submodule {i}",
                "parent_id": "root",
            }
        )
    while len(out) < n:
        out.append(
            {
                "id": f"x{len(out)}",
                "title": f"Extra {len(out)}",
                "parent_id": "c0",
            }
        )
    return out[:n]


def test_rejects_shallow_three_nodes():
    nodes = [
        {"id": "a", "title": "A", "parent_id": None},
        {"id": "b", "title": "B", "parent_id": None},
        {"id": "c", "title": "C", "parent_id": None},
    ]
    ok, msg = validate_syllabus_structure(nodes)
    assert not ok
    assert str(SYLLABUS_MIN_NODES) in msg


def test_rejects_flat_eight_without_children():
    nodes = [{"id": f"n{i}", "title": f"N{i}", "parent_id": None} for i in range(8)]
    ok, msg = validate_syllabus_structure(nodes)
    assert not ok
    assert str(SYLLABUS_MIN_CHILD_NODES) in msg


def test_accepts_module_tree():
    nodes = _nodes(SYLLABUS_MIN_NODES, SYLLABUS_MIN_CHILD_NODES)
    ok, msg = validate_syllabus_structure(nodes)
    assert ok, msg
