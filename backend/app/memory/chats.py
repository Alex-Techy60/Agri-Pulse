"""Saved chats, one history per person (SQLite from the standard library: no new service, no new dependency).

There is no login. The browser makes a long random secret and sends it as X-Client-Id; only its SHA-256 is stored, and
every query is scoped to that owner, so one person's chats cannot be listed, read or deleted with another's id.
Every public method swallows database errors and returns an empty result: history must never break a chat (CLAUDE.md rule 1).
"""
import hashlib
import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger("chats")
CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{24,128}$")  # a guessable id would be a guessable history
CHAT_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_CHATS_PER_OWNER = 100  # oldest-updated chat is dropped past this
MAX_MESSAGES_PER_CHAT = 400
MAX_META_BYTES = 30_000  # cards and sources of one answer; bigger than this is dropped, never truncated mid-JSON
TITLE_CHARS = 60
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "chats.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    owner TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (owner, id));
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, chat_id TEXT NOT NULL,
    role TEXT NOT NULL, text TEXT NOT NULL, meta TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS messages_by_chat ON messages (owner, chat_id, seq);
CREATE TABLE IF NOT EXISTS feedback (
    owner TEXT NOT NULL, message_id INTEGER NOT NULL, value TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (owner, message_id));
"""


def owner_key(client_id: str | None) -> str | None:
    """Hash of the browser's secret, or None when the header is missing or malformed (then nothing is saved)."""
    if not client_id or not CLIENT_ID.match(client_id):
        return None
    return hashlib.sha256(client_id.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _title(text: str) -> str:
    line = " ".join(text.replace("📷", " ").split())
    return (line[:TITLE_CHARS].rstrip() + "…") if len(line) > TITLE_CHARS else (line or "Photo")


class ChatStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()  # SQLite allows one writer; this keeps the cap check and the insert together
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._db() as db:
                db.executescript(_SCHEMA)
        except (sqlite3.Error, OSError) as e:
            log.warning("chat history unavailable: %s", type(e).__name__)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def append_turn(self, owner: str, chat_id: str, user_text: str, bot_text: str, meta: dict | None = None) -> int | None:
        """Save one question and its answer; creates the chat on its first turn. Returns the answer's message id (what feedback refers to), or None if nothing was saved."""
        if not CHAT_ID.match(chat_id):
            return None
        blob = json.dumps(meta or {}, ensure_ascii=False)
        blob = blob if len(blob.encode()) <= MAX_META_BYTES else None
        now = _now()
        try:
            with self._lock, self._db() as db:
                exists = db.execute("SELECT 1 FROM chats WHERE owner=? AND id=?", (owner, chat_id)).fetchone()
                if exists:
                    n = db.execute("SELECT COUNT(*) FROM messages WHERE owner=? AND chat_id=?", (owner, chat_id)).fetchone()[0]
                    if n + 2 > MAX_MESSAGES_PER_CHAT:
                        return None
                    db.execute("UPDATE chats SET updated_at=? WHERE owner=? AND id=?", (now, owner, chat_id))
                else:
                    db.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (owner, chat_id, _title(user_text), now, now))
                    self._trim(db, owner)
                db.execute("INSERT INTO messages (owner, chat_id, role, text, meta, created_at) VALUES (?,?,?,?,?,?)", (owner, chat_id, "user", user_text, None, now))
                cur = db.execute("INSERT INTO messages (owner, chat_id, role, text, meta, created_at) VALUES (?,?,?,?,?,?)", (owner, chat_id, "bot", bot_text, blob, now))
            return cur.lastrowid
        except sqlite3.Error as e:
            log.warning("chat save failed: %s", type(e).__name__)
            return None

    @staticmethod
    def _trim(db: sqlite3.Connection, owner: str) -> None:
        old = [r[0] for r in db.execute("SELECT id FROM chats WHERE owner=? ORDER BY updated_at DESC, rowid DESC LIMIT -1 OFFSET ?", (owner, MAX_CHATS_PER_OWNER))]
        for cid in old:
            db.execute("DELETE FROM messages WHERE owner=? AND chat_id=?", (owner, cid))
            db.execute("DELETE FROM chats WHERE owner=? AND id=?", (owner, cid))

    def list_chats(self, owner: str) -> list[dict]:
        try:
            with self._db() as db:
                rows = db.execute(
                    "SELECT c.id, c.title, c.updated_at, (SELECT COUNT(*) FROM messages m WHERE m.owner=c.owner AND m.chat_id=c.id) AS n "
                    "FROM chats c WHERE c.owner=? ORDER BY c.updated_at DESC, c.rowid DESC", (owner,))
                return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"], "messages": r["n"]} for r in rows]
        except sqlite3.Error as e:
            log.warning("chat list failed: %s", type(e).__name__)
            return []

    def get_chat(self, owner: str, chat_id: str) -> dict | None:
        try:
            with self._db() as db:
                c = db.execute("SELECT id, title, updated_at FROM chats WHERE owner=? AND id=?", (owner, chat_id)).fetchone()
                if not c:
                    return None
                rows = db.execute("SELECT seq, role, text, meta, created_at FROM messages WHERE owner=? AND chat_id=? ORDER BY seq", (owner, chat_id)).fetchall()
                votes = {r["message_id"]: r["value"] for r in db.execute("SELECT message_id, value FROM feedback WHERE owner=?", (owner,))}
        except sqlite3.Error as e:
            log.warning("chat read failed: %s", type(e).__name__)
            return None
        return {"id": c["id"], "title": c["title"], "updated_at": c["updated_at"],
                "messages": [{"id": r["seq"], "role": r["role"], "text": r["text"], "meta": json.loads(r["meta"]) if r["meta"] else {}, "at": r["created_at"], "feedback": votes.get(r["seq"])} for r in rows]}

    def recent(self, owner: str, chat_id: str, n: int) -> list[dict]:
        """The last n messages as LLM turns, so a resumed chat keeps its context after a restart."""
        try:
            with self._db() as db:
                rows = db.execute("SELECT role, text FROM messages WHERE owner=? AND chat_id=? ORDER BY seq DESC LIMIT ?", (owner, chat_id, n)).fetchall()
        except sqlite3.Error:
            return []
        return [{"role": "assistant" if r["role"] == "bot" else "user", "content": r["text"]} for r in reversed(rows)]

    def set_feedback(self, owner: str, message_id: int, value: str | None) -> bool:
        """Thumbs up/down on one of THIS owner's answers (None clears it). False if the answer is not theirs or not an answer."""
        if value not in ("up", "down", None):
            return False
        try:
            with self._lock, self._db() as db:
                if not db.execute("SELECT 1 FROM messages WHERE seq=? AND owner=? AND role='bot'", (message_id, owner)).fetchone():
                    return False
                if value is None:
                    db.execute("DELETE FROM feedback WHERE owner=? AND message_id=?", (owner, message_id))
                else:
                    db.execute("INSERT OR REPLACE INTO feedback VALUES (?,?,?,?)", (owner, message_id, value, _now()))
            return True
        except sqlite3.Error as e:
            log.warning("feedback save failed: %s", type(e).__name__)
            return False

    def delete_chat(self, owner: str, chat_id: str) -> bool:
        try:
            with self._lock, self._db() as db:
                db.execute("DELETE FROM feedback WHERE owner=? AND message_id IN (SELECT seq FROM messages WHERE owner=? AND chat_id=?)", (owner, owner, chat_id))
                db.execute("DELETE FROM messages WHERE owner=? AND chat_id=?", (owner, chat_id))
                return db.execute("DELETE FROM chats WHERE owner=? AND id=?", (owner, chat_id)).rowcount > 0
        except sqlite3.Error as e:
            log.warning("chat delete failed: %s", type(e).__name__)
            return False


_store: ChatStore | None = None


def get_chats() -> ChatStore:
    global _store
    if _store is None:
        configured = get_settings().chat_db_path
        _store = ChatStore(configured or DEFAULT_PATH)
    return _store
