"""Tests for generalized chat dispatch (character / learn) in remote.session."""
import asyncio

import pytest


def _collect(agen):
    async def run():
        out = []
        async for chunk in agen:
            out.append(chunk)
        return out

    return asyncio.run(run())


class FakeAgent:
    def __init__(self, recorder):
        self.recorder = recorder

    def run_character_chat(self, persona, user_input, chat_history, **kw):
        self.recorder["persona"] = persona
        self.recorder["history"] = chat_history
        yield {"message": {"content": "In "}}
        yield {"message": {"content": "character"}}

    def run_learn_tutor_chat(self, course_id, user_input, chat_history, **kw):
        self.recorder["course_id"] = course_id
        self.recorder["node_id"] = kw.get("node_id")
        yield {"message": {"content": "tutor reply"}}

    def run_learn_archive_chat(self, archive_id, archive_title, user_input, chat_history, **kw):
        self.recorder["archive_id"] = archive_id
        self.recorder["archive_title"] = archive_title
        yield {"message": {"content": "archive reply"}}


def test_character_mode_loads_and_saves_history(monkeypatch):
    import main as brain
    import persona_registry as pr
    from remote import session

    rec = {}
    saved = {}

    class P:  # stand-in persona
        id = "vega"
        display_name = "Vega"

    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)
    monkeypatch.setattr(session, "_effective_instance_id", lambda iid: "inst1")
    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeAgent(rec))
    monkeypatch.setattr(pr, "get_persona", lambda iid, pid: P())
    monkeypatch.setattr(pr, "load_chat_history", lambda iid, pid: [{"role": "user", "content": "earlier"}])
    monkeypatch.setattr(pr, "save_chat_history", lambda iid, pid, msgs: saved.update({"msgs": msgs, "pid": pid}))

    chunks = _collect(
        session.stream_chat_chunks(
            instance_id="inst1", message="hi", history=[], mode="character", persona_id="vega"
        )
    )
    text = "".join((c.get("message", {}) or {}).get("content", "") for c in chunks)
    assert text == "In character"
    # History authoritative: prior turn + new user/assistant pair persisted.
    assert saved["pid"] == "vega"
    assert saved["msgs"][-2] == {"role": "user", "content": "hi"}
    assert saved["msgs"][-1] == {"role": "assistant", "content": "In character"}


def test_learn_tutor_mode_sets_runtime_and_node(monkeypatch):
    import main as brain
    import learn_registry as lr
    from remote import session
    from tool_library import learn_tools

    rec = {}
    runtime = {}

    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)
    monkeypatch.setattr(session, "_effective_instance_id", lambda iid: "inst1")
    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeAgent(rec))
    monkeypatch.setattr(lr, "load_tutor_history", lambda iid, cid: [])
    monkeypatch.setattr(lr, "save_tutor_history", lambda iid, cid, msgs: None)
    monkeypatch.setattr(
        learn_tools, "set_learn_runtime",
        lambda iid, course_id="", archive_id="": runtime.update({"course_id": course_id}),
    )

    chunks = _collect(
        session.stream_chat_chunks(
            instance_id="inst1", message="explain", history=[], mode="learn_tutor",
            course_id="c1", node_id="n2",
        )
    )
    text = "".join((c.get("message", {}) or {}).get("content", "") for c in chunks)
    assert text == "tutor reply"
    assert rec["course_id"] == "c1"
    assert rec["node_id"] == "n2"
    assert runtime["course_id"] == "c1"


def test_archive_mode_uses_title(monkeypatch):
    import main as brain
    import learn_registry as lr
    from remote import session
    from tool_library import learn_tools

    rec = {}

    class A:
        title = "My Archive"

    monkeypatch.setattr(session, "_apply_instance_model", lambda iid: None)
    monkeypatch.setattr(session, "_effective_instance_id", lambda iid: "inst1")
    monkeypatch.setattr(brain, "get_agent", lambda iid=None: FakeAgent(rec))
    monkeypatch.setattr(lr, "get_archive", lambda iid, aid: A())
    monkeypatch.setattr(lr, "load_archive_chat_history", lambda iid, aid: [])
    monkeypatch.setattr(lr, "save_archive_chat_history", lambda iid, aid, msgs: None)
    monkeypatch.setattr(learn_tools, "set_learn_runtime", lambda iid, course_id="", archive_id="": None)

    chunks = _collect(
        session.stream_chat_chunks(
            instance_id="inst1", message="q", history=[], mode="learn_archive", archive_id="a1"
        )
    )
    text = "".join((c.get("message", {}) or {}).get("content", "") for c in chunks)
    assert text == "archive reply"
    assert rec["archive_id"] == "a1"
    assert rec["archive_title"] == "My Archive"
