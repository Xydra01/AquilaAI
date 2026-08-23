import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_create_and_list_threads(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from agent.storage import create_thread, list_threads

    t1 = create_thread("default", "First discussion")
    t2 = create_thread("default", "Second discussion")
    threads = list_threads("default")
    ids = [t.id for t in threads]
    assert t1.id in ids
    assert t2.id in ids


def test_save_and_load_thread_history(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from agent.storage import create_thread, load_thread_history, save_thread_history

    t = create_thread("default", "Mongol Empire")
    msgs = [
        {"role": "user", "content": "Who was Genghis Khan?"},
        {"role": "assistant", "content": "Founder of the Mongol Empire."},
    ]
    save_thread_history("default", t.id, msgs)
    out = load_thread_history("default", t.id)
    assert out == msgs


def test_regenerate_and_edit_last_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from agent.storage import (
        create_thread,
        save_thread_history,
        regenerate_last_turn,
        edit_last_user_turn,
        load_thread_history,
    )

    t = create_thread("default", "Test")
    save_thread_history(
        "default",
        t.id,
        [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ],
    )
    hist, prompt = regenerate_last_turn("default", t.id)
    assert prompt == "q2"
    assert hist[-1]["role"] == "user"
    edited = edit_last_user_turn("default", t.id, "q2-edited")
    assert edited[-1]["content"] == "q2-edited"
    assert load_thread_history("default", t.id)[-1]["content"] == "q2-edited"
