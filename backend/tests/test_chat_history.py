"""Saved chats: one history per person, resumable, deletable. No network, no keys; each test gets its own SQLite file."""
import pytest

from app.agents.orchestrator import Orchestrator
from app.memory.chats import ChatStore, owner_key
from tests.helpers import FakeLLM, StubStore
from tests.test_pipeline import domain, good

ALICE_ID, BOB_ID = "a" * 32, "b" * 32
ALICE, BOB = owner_key(ALICE_ID), owner_key(BOB_ID)


@pytest.fixture
def store(tmp_path):
    return ChatStore(tmp_path / "chats.db")


# ----------------------------------------------------------------- the store
def test_owner_key_hashes_the_secret_and_rejects_short_or_odd_ids():
    assert owner_key(ALICE_ID) != ALICE_ID and len(owner_key(ALICE_ID)) == 64
    assert owner_key(None) is None and owner_key("short") is None and owner_key("x" * 30 + "!") is None


def test_turns_are_saved_in_order_with_meta_and_a_title(store):
    store.append_turn(ALICE, "chat-0001", "Should I sell my onions now?", "Hold for now.", {"cards": [{"type": "price"}], "degraded": False})
    store.append_turn(ALICE, "chat-0001", "And tomorrow?", "Same.", {})
    chat = store.get_chat(ALICE, "chat-0001")
    assert chat["title"] == "Should I sell my onions now?"
    assert [(m["role"], m["text"]) for m in chat["messages"]] == [("user", "Should I sell my onions now?"), ("bot", "Hold for now."), ("user", "And tomorrow?"), ("bot", "Same.")]
    assert chat["messages"][1]["meta"]["cards"] == [{"type": "price"}]
    assert [c["messages"] for c in store.list_chats(ALICE)] == [4]


def test_devanagari_text_round_trips(store):
    store.append_turn(ALICE, "chat-0001", "मी कांदा विकू का?", "आता थांबा.", {})
    assert store.get_chat(ALICE, "chat-0001")["messages"][0]["text"] == "मी कांदा विकू का?"


def test_people_never_see_each_others_chats(store):
    store.append_turn(ALICE, "shared-id-1", "alice question", "a", {})
    store.append_turn(BOB, "shared-id-1", "bob question", "b", {})  # even the same chat id is a different chat
    assert store.get_chat(BOB, "shared-id-1")["messages"][0]["text"] == "bob question"
    assert [c["title"] for c in store.list_chats(ALICE)] == ["alice question"]
    assert store.delete_chat(BOB, "shared-id-1") and store.get_chat(ALICE, "shared-id-1") is not None
    assert store.get_chat(owner_key("c" * 32), "shared-id-1") is None


def test_list_is_newest_first_and_delete_removes_messages(store):
    store.append_turn(ALICE, "chat-0001", "first", "x", {})
    store.append_turn(ALICE, "chat-0002", "second", "x", {})
    store.append_turn(ALICE, "chat-0001", "first again", "x", {})  # touching a chat moves it to the top
    assert [c["id"] for c in store.list_chats(ALICE)] == ["chat-0001", "chat-0002"]
    assert store.delete_chat(ALICE, "chat-0001") and not store.delete_chat(ALICE, "chat-0001")
    assert store.get_chat(ALICE, "chat-0001") is None and store.recent(ALICE, "chat-0001", 10) == []


def test_recent_returns_llm_turns_oldest_first(store):
    store.append_turn(ALICE, "chat-0001", "q1", "a1", {})
    store.append_turn(ALICE, "chat-0001", "q2", "a2", {})
    assert store.recent(ALICE, "chat-0001", 3) == [{"role": "assistant", "content": "a1"}, {"role": "user", "content": "q2"}, {"role": "assistant", "content": "a2"}]


def test_caps_keep_the_database_small(store, monkeypatch):
    import app.memory.chats as chats
    monkeypatch.setattr(chats, "MAX_CHATS_PER_OWNER", 2)
    for i in range(4):
        store.append_turn(ALICE, f"chat-000{i}", f"q{i}", "a", {})
    assert [c["id"] for c in store.list_chats(ALICE)] == ["chat-0003", "chat-0002"]
    monkeypatch.setattr(chats, "MAX_MESSAGES_PER_CHAT", 2)
    assert store.append_turn(ALICE, "chat-0003", "one too many", "a", {}) is None
    assert store.append_turn(ALICE, "chat-0003", "x", "a", {"big": "y" * 40_000}) is None  # chat is full; and an oversized meta is dropped below
    monkeypatch.setattr(chats, "MAX_MESSAGES_PER_CHAT", 400)
    assert store.append_turn(ALICE, "chat-0003", "big card", "a", {"big": "y" * 40_000}) is not None
    assert store.get_chat(ALICE, "chat-0003")["messages"][-1]["meta"] == {}  # text kept, oversized meta dropped


def test_bad_chat_id_and_unwritable_database_never_raise(store, tmp_path):
    assert store.append_turn(ALICE, "../etc", "q", "a", {}) is None
    broken = ChatStore(tmp_path)  # a directory, not a file
    assert broken.append_turn(ALICE, "chat-0001", "q", "a", {}) is None
    assert broken.list_chats(ALICE) == [] and broken.get_chat(ALICE, "chat-0001") is None and broken.recent(ALICE, "chat-0001", 4) == []


# ------------------------------------------------- continuing after a restart
def test_resumed_chat_gives_the_model_its_earlier_turns_back():
    llm = FakeLLM(["Max 33 C."])
    o = Orchestrator(domain(["good"]), llm, StubStore())
    o.restore_history("s1", [{"role": "user", "content": "earlier question"}, {"role": "assistant", "content": "earlier answer"}])
    o.run("and now?", "s1", "en", None, {})
    assert {"role": "user", "content": "earlier question"} in llm.last_messages


def test_restore_never_overwrites_live_history_or_the_shared_session():
    o = Orchestrator(domain(["good"]), FakeLLM(["Max 33 C."]), StubStore())
    o.run("first", "s1", "en", None, {})
    o.restore_history("s1", [{"role": "user", "content": "stale"}])
    o.restore_history("default", [{"role": "user", "content": "leak"}])
    assert all(m["content"] != "stale" for m in o.history["s1"]) and "default" not in o.history


def test_forget_history_clears_context_profile_and_vector_memory():
    store = StubStore()
    store.forgotten = []
    store.forget_session = store.forgotten.append
    o = Orchestrator(domain(["good"]), FakeLLM(["Max 33 C."]), store)
    o.run("first", "s1", "en", None, {"crop": "Onion"})
    o.forget_history("s1")
    assert "s1" not in o.history and "s1" not in o.profiles and store.forgotten == ["s1"]


# ------------------------------------------------------------------- routes
@pytest.fixture
def client(store, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.routes as routes
    from app.main import app

    monkeypatch.setattr(routes, "get_chats", lambda: store)
    with TestClient(app) as c:
        yield c


def h(client_id):
    return {"X-Client-Id": client_id}


def test_chat_is_saved_listed_and_reloaded_per_person(client):
    r = client.post("/api/chat", json={"message": "hello", "session_id": "chat-0001"}, headers=h(ALICE_ID))
    assert r.status_code == 200 and r.json()["answer"]
    client.post("/api/chat/stream", json={"message": "hi again", "session_id": "chat-0002"}, headers=h(ALICE_ID))

    mine = client.get("/api/chats", headers=h(ALICE_ID)).json()["chats"]
    assert [c["id"] for c in mine] == ["chat-0002", "chat-0001"]
    chat = client.get("/api/chats/chat-0001", headers=h(ALICE_ID)).json()
    assert {k: chat["messages"][0][k] for k in ("role", "text", "meta")} == {"role": "user", "text": "hello", "meta": {}} and chat["messages"][0]["at"] and chat["messages"][1]["text"] == r.json()["answer"]

    assert client.get("/api/chats", headers=h(BOB_ID)).json() == {"chats": []}
    assert client.get("/api/chats/chat-0001", headers=h(BOB_ID)).status_code == 404
    assert client.delete("/api/chats/chat-0001", headers=h(BOB_ID)).status_code == 404


def test_delete_removes_the_chat(client):
    client.post("/api/chat", json={"message": "hello", "session_id": "chat-0001"}, headers=h(ALICE_ID))
    assert client.delete("/api/chats/chat-0001", headers=h(ALICE_ID)).json() == {"deleted": True}
    assert client.get("/api/chats/chat-0001", headers=h(ALICE_ID)).status_code == 404


def test_without_a_client_id_chat_works_but_nothing_is_saved(client, store):
    assert client.post("/api/chat", json={"message": "hello", "session_id": "chat-0001"}).status_code == 200
    assert client.get("/api/chats").status_code == 400 and client.get("/api/chats/chat-0001", headers=h("short")).status_code == 400
    assert store.list_chats(ALICE) == []


def test_internal_errors_and_empty_questions_are_not_saved(client, store, monkeypatch):
    import app.api.routes as routes
    client.post("/api/chat", json={"message": "   ", "session_id": "chat-0001"}, headers=h(ALICE_ID))
    monkeypatch.setattr(routes, "get_orchestrator", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    r = client.post("/api/chat", json={"message": "hello", "session_id": "chat-0002"}, headers=h(ALICE_ID))
    assert r.status_code == 200 and r.json()["degraded"] and store.list_chats(ALICE) == []


def test_two_people_choosing_the_same_chat_id_do_not_share_model_context(client):
    client.post("/api/chat", json={"message": "alice secret", "session_id": "same-id-1"}, headers=h(ALICE_ID))
    import app.api.routes as routes
    hist = routes.get_orchestrator().history
    keys = [k for k in hist if k.endswith(":same-id-1")]
    assert keys == [f"{ALICE[:16]}:same-id-1"] and f"{BOB[:16]}:same-id-1" not in hist


# ----------------------------------------------------------------- feedback
def test_feedback_is_saved_cleared_and_returned_with_the_chat(store):
    mid = store.append_turn(ALICE, "chat-0001", "q", "a", {})
    assert isinstance(mid, int)
    assert store.set_feedback(ALICE, mid, "down") and store.set_feedback(ALICE, mid, "up")  # changing your mind replaces the vote
    bot = store.get_chat(ALICE, "chat-0001")["messages"][1]
    assert bot["id"] == mid and bot["feedback"] == "up" and store.get_chat(ALICE, "chat-0001")["messages"][0]["feedback"] is None
    assert store.set_feedback(ALICE, mid, None) and store.get_chat(ALICE, "chat-0001")["messages"][1]["feedback"] is None


def test_feedback_only_on_your_own_answers_with_valid_values(store):
    mid = store.append_turn(ALICE, "chat-0001", "q", "a", {})
    user_msg = mid - 1
    assert not store.set_feedback(BOB, mid, "up")  # someone else's answer
    assert not store.set_feedback(ALICE, user_msg, "up")  # a question is not an answer
    assert not store.set_feedback(ALICE, 99999, "up") and not store.set_feedback(ALICE, mid, "maybe")
    assert store.get_chat(ALICE, "chat-0001")["messages"][1]["feedback"] is None


def test_deleting_a_chat_deletes_its_feedback(store):
    mid = store.append_turn(ALICE, "chat-0001", "q", "a", {})
    store.set_feedback(ALICE, mid, "up")
    store.delete_chat(ALICE, "chat-0001")
    import sqlite3
    assert sqlite3.connect(store.path).execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 0


def test_feedback_route_end_to_end(client):
    r = client.post("/api/chat", json={"message": "hello", "session_id": "chat-0001"}, headers=h(ALICE_ID)).json()
    mid = r["message_id"]
    assert isinstance(mid, int)
    assert client.put("/api/feedback", json={"message_id": mid, "value": "up"}, headers=h(ALICE_ID)).json() == {"ok": True}
    assert client.get("/api/chats/chat-0001", headers=h(ALICE_ID)).json()["messages"][1]["feedback"] == "up"
    assert client.put("/api/feedback", json={"message_id": mid, "value": "up"}, headers=h(BOB_ID)).status_code == 404
    assert client.put("/api/feedback", json={"message_id": mid, "value": "maybe"}, headers=h(ALICE_ID)).status_code == 422
    assert client.put("/api/feedback", json={"message_id": mid, "value": "up"}).status_code == 400  # no client id
    assert client.put("/api/feedback", json={"message_id": mid, "value": None}, headers=h(ALICE_ID)).status_code == 200
