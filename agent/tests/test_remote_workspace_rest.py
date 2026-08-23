"""Tests for Character + Learn REST endpoints (registries mocked)."""
import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUILA_DATA_ROOT", str(tmp_path))
    from remote import server

    with TestClient(server.app) as c:
        yield c


def _pair(client):
    from remote import auth

    return client.post(
        "/api/pair",
        json={"host_id": auth.get_host_id(), "pairing_code": auth.generate_pairing_code(), "device_name": "t"},
    ).json()["token"]


def _h(client):
    return {"Authorization": f"Bearer {_pair(client)}"}


def test_character_list_and_create(client, monkeypatch):
    from remote import personas

    monkeypatch.setattr(personas, "list_personas", lambda iid: [{"id": "vega", "display_name": "Vega", "build_complete": True}])
    monkeypatch.setattr(
        personas, "create_persona_for_build",
        lambda iid, name, desc, lore: {
            "persona": {"id": "vega", "display_name": name},
            "task_name": "persona_build_vega",
            "mode": "character_build",
            "prompt": "build it",
            "persona_research_lore": lore,
        },
    )
    h = _h(client)

    r = client.get("/api/character/personas", headers=h)
    assert r.status_code == 200
    assert r.json()["personas"][0]["id"] == "vega"

    r = client.post(
        "/api/character/personas",
        headers=h,
        json={"display_name": "Vega", "description": "captain", "research_lore": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_name"] == "persona_build_vega"
    assert body["mode"] == "character_build"
    assert body["persona_research_lore"] is True


def test_character_create_requires_name(client):
    r = client.post("/api/character/personas", headers=_h(client), json={"display_name": "  "})
    assert r.status_code == 400


def test_character_preferences_roundtrip(client, monkeypatch):
    from remote import personas

    store = {"text": "likes coffee"}
    monkeypatch.setattr(personas, "load_preferences", lambda iid, pid: store["text"])
    monkeypatch.setattr(personas, "save_preferences", lambda iid, pid, text: store.update({"text": text}))
    h = _h(client)

    r = client.get("/api/character/personas/vega/preferences", headers=h)
    assert r.json()["text"] == "likes coffee"

    r = client.put("/api/character/personas/vega/preferences", headers=h, json={"text": "likes tea"})
    assert r.status_code == 200
    assert store["text"] == "likes tea"


def test_learn_courses_list_and_create(client, monkeypatch):
    from remote import learn

    monkeypatch.setattr(learn, "list_courses", lambda iid: [{"id": "c1", "title": "Astro", "build_complete": False}])
    monkeypatch.setattr(
        learn, "create_course_for_build",
        lambda iid, title, topic, intake, web: {
            "course": {"id": "c1", "title": title},
            "task_name": "syllabus_build_c1",
            "mode": "learn_syllabus_build",
            "prompt": "build syllabus",
            "learn_syllabus_web": web,
        },
    )
    h = _h(client)

    r = client.get("/api/learn/courses", headers=h)
    assert r.json()["courses"][0]["id"] == "c1"

    r = client.post("/api/learn/courses", headers=h, json={"title": "Astro", "web": True})
    assert r.status_code == 200
    assert r.json()["task_name"] == "syllabus_build_c1"
    assert r.json()["learn_syllabus_web"] is True


def test_learn_assessment_submit(client, monkeypatch):
    from remote import learn

    captured = {}
    monkeypatch.setattr(
        learn, "submit_assessment",
        lambda iid, cid, node_id, aid, score: captured.update(
            {"cid": cid, "node": node_id, "aid": aid, "score": score}
        ) or {"message": "passed", "syllabus": {}},
    )
    h = _h(client)
    r = client.post(
        "/api/learn/courses/c1/assessments/submit",
        headers=h,
        json={"node_id": "n1", "assessment_id": "a1", "score": 85},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "passed"
    assert captured["score"] == 85


def test_learn_archives_list_and_create(client, monkeypatch):
    from remote import learn

    monkeypatch.setattr(learn, "list_archives", lambda iid: [{"id": "a1", "title": "Docs"}])
    monkeypatch.setattr(learn, "create_archive", lambda iid, title: {"id": "a2", "title": title})
    h = _h(client)

    r = client.get("/api/learn/archives", headers=h)
    assert r.json()["archives"][0]["id"] == "a1"

    r = client.post("/api/learn/archives", headers=h, json={"title": "Papers"})
    assert r.status_code == 200
    assert r.json()["archive"]["title"] == "Papers"
