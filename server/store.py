from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory: Path, identity: str):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.path = directory / "control.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, csrf TEXT NOT NULL, fingerprint TEXT NOT NULL, expires REAL NOT NULL, client TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS confirmations (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, action TEXT NOT NULL, region TEXT NOT NULL, resource_id TEXT NOT NULL, params TEXT NOT NULL, preview TEXT NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL DEFAULT 'prepared', idempotency_key TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, resourceName TEXT NOT NULL, region TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS login_attempts (at REAL NOT NULL, peer TEXT NOT NULL);
            """)
            old = db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
            if old and old[0] != identity:
                db.executescript("DELETE FROM sessions; DELETE FROM confirmations; DELETE FROM audit; DELETE FROM meta;")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('identity', ?)", (identity,))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('serverId', ?)", (str(uuid.uuid4()),))
            # An interrupted provider request has an unknown outcome; never retry it automatically.
            db.execute("UPDATE confirmations SET state='unknown' WHERE state='executing'")
            db.execute("UPDATE audit SET status='unknown', message='服务在操作过程中退出，结果待核对。请先刷新资源状态，勿重复提交。' WHERE status='executing'")
        self.path.chmod(0o600)
        self.server_id = self.get_meta("serverId")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get_meta(self, key):
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def set_meta(self, key, value):
        with self.connect() as db:
            db.execute("INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def attempt_login(self, peer):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE at < ?", (now - 300,))
            n = db.execute("SELECT count(*) FROM login_attempts WHERE peer=?", (peer,)).fetchone()[0]
            total = db.execute("SELECT count(*) FROM login_attempts").fetchone()[0]
            if n >= 10 or total >= 50:
                return False
            db.execute("INSERT INTO login_attempts VALUES (?,?)", (now, peer))
            return True

    def create_session(self, session_id, csrf, fingerprint, seconds, client):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ? OR fingerprint != ?", (time.time(), fingerprint))
            db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (session_id, csrf, fingerprint, time.time() + seconds, client))

    def get_session(self, session_id, fingerprint, seconds):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=? AND fingerprint=? AND expires>?", (session_id, fingerprint, time.time())).fetchone()
            if row:
                db.execute("UPDATE sessions SET expires=? WHERE id=?", (time.time() + seconds, session_id))
                return dict(row)
        return None

    def revoke_session(self, session_id):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            db.execute("DELETE FROM confirmations WHERE session_id=? AND state='prepared'", (session_id,))

    def prepare(self, session_id, action, region, resource_id, params, preview):
        ident = str(uuid.uuid4())
        expires = time.time() + 120
        with self.connect() as db:
            db.execute("DELETE FROM confirmations WHERE state='prepared' AND expires < ?", (time.time(),))
            db.execute("INSERT INTO confirmations(id,session_id,action,region,resource_id,params,preview,expires) VALUES (?,?,?,?,?,?,?,?)", (ident, session_id, action, region, resource_id, json.dumps(params), json.dumps(preview), expires))
        return ident, expires

    def confirmation(self, ident, session_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM confirmations WHERE id=? AND session_id=?", (ident, session_id)).fetchone()
            return dict(row) if row else None

    def claim(self, ident, session_id, key):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM confirmations WHERE id=? AND session_id=?", (ident, session_id)).fetchone()
            if not row:
                return "missing", None
            if row["state"] != "prepared":
                if row["state"] == "succeeded" and row["idempotency_key"] == key:
                    return "replayed", json.loads(row["result"])
                return row["state"], None
            if row["expires"] < time.time():
                return "expired", None
            duplicate = db.execute("SELECT id FROM confirmations WHERE session_id=? AND idempotency_key=?", (session_id, key)).fetchone()
            if duplicate:
                return "duplicate", None
            db.execute("UPDATE confirmations SET state='executing',idempotency_key=? WHERE id=?", (key, ident))
            from datetime import datetime, timezone
            preview = json.loads(row["preview"])
            db.execute("INSERT INTO audit VALUES (?,?,?,?,?,?,?)", (ident, datetime.now(timezone.utc).isoformat(), row["action"], preview.get("resourceName", row["resource_id"]), row["region"], "executing", "操作已确认，正在向云端提交。"))
            return "claimed", dict(row)

    def finish(self, ident, state, result):
        with self.connect() as db:
            db.execute("UPDATE confirmations SET state=?,result=? WHERE id=?", (state, json.dumps(result), ident))
            db.execute("UPDATE audit SET status=?,message=? WHERE id=?", (result.get("status", state), result.get("message", "操作未完成，请核对资源状态。"), ident))

    def audit(self, action, name, region, status, message):
        from datetime import datetime, timezone
        with self.connect() as db:
            db.execute("INSERT INTO audit VALUES (?,?,?,?,?,?,?)", (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), action, name, region, status, message))

    def audit_events(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM audit ORDER BY at DESC LIMIT 100")]
