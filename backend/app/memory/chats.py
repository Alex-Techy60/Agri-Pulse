"""Saved chats, one history per person. Two backends behind one class: hosted Postgres (DATABASE_URL, e.g. Neon: survives
redeploys) or SQLite (zero setup, the automatic fallback when DATABASE_URL is empty or unreachable).

Anonymous visitors are keyed by a long random secret the browser sends as X-Client-Id; signed-in people by their Google
account. Only a SHA-256 of either is stored, and every query is scoped to that owner, so one person's chats cannot be listed,
read or deleted with another's id. Every public method swallows database errors and returns an empty result: history must
never break a chat (CLAUDE.md rule 1).
"""
import hashlib
import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
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
    seq {SEQ}, owner TEXT NOT NULL, chat_id TEXT NOT NULL,
    role TEXT NOT NULL, text TEXT NOT NULL, meta TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS messages_by_chat ON messages (owner, chat_id, seq);
CREATE TABLE IF NOT EXISTS feedback (
    owner TEXT NOT NULL, message_id INTEGER NOT NULL, value TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (owner, message_id));
CREATE TABLE IF NOT EXISTS prefs (
    owner TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
    sub TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL, picture TEXT NOT NULL, created_at TEXT NOT NULL, last_login TEXT NOT NULL);
"""
_SEQ = {"sqlite": "INTEGER PRIMARY KEY AUTOINCREMENT", "postgres": "BIGSERIAL PRIMARY KEY"}


class _PgConn:
    """Lets the shared SQL (written with `?`) run on psycopg, which wants `%s`."""
    def __init__(self, conn):
        self._c = conn

    def execute(self, sql: str, params: tuple = ()):
        return self._c.execute(sql.replace("?", "%s"), params)


# Everything a database can throw at us. psycopg is imported lazily so SQLite-only installs never load it.
def _errors() -> tuple:
    try:
        import psycopg
        import psycopg_pool
        return (sqlite3.Error, psycopg.Error, psycopg_pool.PoolTimeout)
    except ImportError:
        return (sqlite3.Error,)


DB_ERRORS = _errors()


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
    def __init__(self, path: Path | str | None = None, database_url: str = ""):
        """Postgres when `database_url` is given, otherwise a SQLite file at `path`. Raises if Postgres cannot be reached
        (get_chats() then falls back to SQLite); a SQLite problem is logged and every call degrades to an empty result."""
        self._lock = threading.Lock()  # keeps the cap check and the insert together
        self.pg = bool(database_url)
        self.dialect = "postgres" if self.pg else "sqlite"
        self.path = Path(path) if path else DEFAULT_PATH
        schema = _SCHEMA.replace("{SEQ}", _SEQ[self.dialect])
        if self.pg:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            self._pool = ConnectionPool(database_url, min_size=1, max_size=5, timeout=8, open=False,
                                        kwargs={"row_factory": dict_row, "connect_timeout": 8}, check=ConnectionPool.check_connection)
            self._pool.open(wait=True, timeout=10)  # raises when unreachable
            with self._db() as db:
                for stmt in filter(str.strip, schema.split(";")):
                    db.execute(stmt)
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._db() as db:
                db.executescript(schema)
        except (sqlite3.Error, OSError) as e:
            log.warning("chat history unavailable: %s", type(e).__name__)

    @contextmanager
    def _db(self):
        """A connection that commits on success. Both backends take `?` placeholders (translated for Postgres) and return dict-like rows."""
        if self.pg:
            with self._pool.connection() as conn:
                yield _PgConn(conn)
            return
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

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
                    n = db.execute("SELECT COUNT(*) AS n FROM messages WHERE owner=? AND chat_id=?", (owner, chat_id)).fetchone()["n"]
                    if n + 2 > MAX_MESSAGES_PER_CHAT:
                        return None
                    db.execute("UPDATE chats SET updated_at=? WHERE owner=? AND id=?", (now, owner, chat_id))
                else:
                    db.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (owner, chat_id, _title(user_text), now, now))
                    self._trim(db, owner)
                db.execute("INSERT INTO messages (owner, chat_id, role, text, meta, created_at) VALUES (?,?,?,?,?,?)", (owner, chat_id, "user", user_text, None, now))
                row = db.execute("INSERT INTO messages (owner, chat_id, role, text, meta, created_at) VALUES (?,?,?,?,?,?) RETURNING seq", (owner, chat_id, "bot", bot_text, blob, now)).fetchone()
            return row["seq"]
        except DB_ERRORS as e:
            log.warning("chat save failed: %s", type(e).__name__)
            return None

    @staticmethod
    def _trim(db, owner: str) -> None:
        old = [r["id"] for r in db.execute("SELECT id FROM chats WHERE owner=? ORDER BY updated_at DESC, created_at DESC", (owner,))][MAX_CHATS_PER_OWNER:]
        for cid in old:
            db.execute("DELETE FROM messages WHERE owner=? AND chat_id=?", (owner, cid))
            db.execute("DELETE FROM chats WHERE owner=? AND id=?", (owner, cid))

    def list_chats(self, owner: str) -> list[dict]:
        try:
            with self._db() as db:
                rows = db.execute(
                    "SELECT c.id, c.title, c.updated_at, (SELECT COUNT(*) FROM messages m WHERE m.owner=c.owner AND m.chat_id=c.id) AS n "
                    "FROM chats c WHERE c.owner=? ORDER BY c.updated_at DESC, c.created_at DESC", (owner,))
                return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"], "messages": r["n"]} for r in rows]
        except DB_ERRORS as e:
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
        except DB_ERRORS as e:
            log.warning("chat read failed: %s", type(e).__name__)
            return None
        return {"id": c["id"], "title": c["title"], "updated_at": c["updated_at"],
                "messages": [{"id": r["seq"], "role": r["role"], "text": r["text"], "meta": json.loads(r["meta"]) if r["meta"] else {}, "at": r["created_at"], "feedback": votes.get(r["seq"])} for r in rows]}

    def recent(self, owner: str, chat_id: str, n: int) -> list[dict]:
        """The last n messages as LLM turns, so a resumed chat keeps its context after a restart."""
        try:
            with self._db() as db:
                rows = db.execute("SELECT role, text FROM messages WHERE owner=? AND chat_id=? ORDER BY seq DESC LIMIT ?", (owner, chat_id, n)).fetchall()
        except DB_ERRORS:
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
                    db.execute("INSERT INTO feedback VALUES (?,?,?,?) ON CONFLICT (owner, message_id) DO UPDATE SET value=excluded.value, created_at=excluded.created_at", (owner, message_id, value, _now()))
            return True
        except DB_ERRORS as e:
            log.warning("feedback save failed: %s", type(e).__name__)
            return False

    def delete_chat(self, owner: str, chat_id: str) -> bool:
        try:
            with self._lock, self._db() as db:
                db.execute("DELETE FROM feedback WHERE owner=? AND message_id IN (SELECT seq FROM messages WHERE owner=? AND chat_id=?)", (owner, owner, chat_id))
                db.execute("DELETE FROM messages WHERE owner=? AND chat_id=?", (owner, chat_id))
                return db.execute("DELETE FROM chats WHERE owner=? AND id=?", (owner, chat_id)).rowcount > 0
        except DB_ERRORS as e:
            log.warning("chat delete failed: %s", type(e).__name__)
            return False


    def adopt(self, from_owner: str, to_owner: str) -> int:
        """Move an anonymous browser's chats into a Google account at sign-in, so nothing said before logging in is lost.
        All three tables move together or not at all. Returns how many chats moved."""
        if not from_owner or from_owner == to_owner:
            return 0
        try:
            with self._lock, self._db() as db:
                n = db.execute("SELECT COUNT(*) AS n FROM chats WHERE owner=?", (from_owner,)).fetchone()["n"]
                for t in ("chats", "messages", "feedback"):
                    db.execute(f"UPDATE {t} SET owner=? WHERE owner=?", (to_owner, from_owner))
                # settings: the account's own win; the browser's are taken only if the account has none yet
                db.execute("UPDATE prefs SET owner=? WHERE owner=? AND NOT EXISTS (SELECT 1 FROM prefs WHERE owner=?)", (to_owner, from_owner, to_owner))
                db.execute("DELETE FROM prefs WHERE owner=?", (from_owner,))
            return n
        except DB_ERRORS as e:  # e.g. a chat id both sides share: keep the chats where they are rather than lose any
            log.warning("chat adopt failed: %s", type(e).__name__)
            return 0

    def load_prefs(self, owner: str) -> dict:
        """This person's saved settings (language, profile, read-aloud...), or {} if none or the database is down."""
        try:
            with self._db() as db:
                row = db.execute("SELECT data FROM prefs WHERE owner=?", (owner,)).fetchone()
            return json.loads(row["data"]) if row else {}
        except (*DB_ERRORS, ValueError) as e:
            log.warning("settings read failed: %s", type(e).__name__)
            return {}

    def save_prefs(self, owner: str, data: dict) -> bool:
        try:
            with self._lock, self._db() as db:
                db.execute("INSERT INTO prefs VALUES (?,?,?) ON CONFLICT (owner) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                           (owner, json.dumps(data, ensure_ascii=False), _now()))
            return True
        except DB_ERRORS as e:
            log.warning("settings save failed: %s", type(e).__name__)
            return False

    def record_user(self, user: dict) -> None:
        """Remember who signed in (Google account id, name, email, photo). Best effort: sign-in works even if this fails."""
        now = _now()
        try:
            with self._lock, self._db() as db:
                db.execute("INSERT INTO users VALUES (?,?,?,?,?,?) ON CONFLICT (sub) DO UPDATE SET email=excluded.email, name=excluded.name, picture=excluded.picture, last_login=excluded.last_login",
                           (user["sub"], user.get("email", ""), user.get("name", ""), user.get("picture", ""), now, now))
        except DB_ERRORS as e:
            log.warning("user save failed: %s", type(e).__name__)

    def count_users(self) -> int:
        try:
            with self._db() as db:
                return db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        except DB_ERRORS:
            return 0


_store: ChatStore | None = None


def get_chats() -> ChatStore:
    global _store
    if _store is None:
        cfg = get_settings()
        if cfg.database_url.strip():
            try:
                _store = ChatStore(database_url=cfg.database_url.strip())
                log.info("chat history: Postgres")
                return _store
            except Exception as e:  # unreachable, wrong password, driver missing: the demo must still run
                log.warning("DATABASE_URL set but unusable (%s): falling back to SQLite", type(e).__name__)
        _store = ChatStore(cfg.chat_db_path or DEFAULT_PATH)
    return _store
