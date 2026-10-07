"""Durable transactions own workflow state. Network/model calls never hold a transaction."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from signalbrief.schemas import Event
from signalbrief.database import postgres_schema, postgres_transaction


class Conflict(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class Store:
    def __init__(self, path: Path, database_url: str = ""):
        self.path = path
        self.database_url = database_url

    @contextmanager
    def transaction(self):
        if self.database_url:
            with postgres_transaction(self.database_url) as conn:
                yield conn
            return
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        schema = """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, event_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'queued',
                    created_at REAL NOT NULL, updated_at REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
                    lease_token TEXT, lease_until REAL, error TEXT,
                    sources_json TEXT, research_json TEXT, report_json TEXT,
                    messages_json TEXT, metrics_json TEXT, feedback TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                    created_at REAL NOT NULL, event TEXT NOT NULL, details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    run_id TEXT NOT NULL REFERENCES runs(id), version INTEGER NOT NULL,
                    created_at REAL NOT NULL, research_json TEXT NOT NULL, report_json TEXT NOT NULL,
                    messages_json TEXT NOT NULL, metrics_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, version)
                );
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), version INTEGER NOT NULL,
                    kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL, available_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, lease_token TEXT, lease_until REAL,
                    error TEXT, receipt_json TEXT, UNIQUE(run_id, version, kind)
                );
                CREATE INDEX IF NOT EXISTS runs_queue ON runs(status, available_at, lease_until);
                CREATE INDEX IF NOT EXISTS deliveries_queue ON deliveries(status, available_at, lease_until);
                CREATE INDEX IF NOT EXISTS audit_run ON audit(run_id, id);
                CREATE TABLE IF NOT EXISTS worker_health (
                    id TEXT PRIMARY KEY, last_seen REAL NOT NULL
                );
            """
        if self.database_url:
            with self.transaction() as conn:
                for statement in postgres_schema(schema).split(";"):
                    if statement.strip():
                        conn.execute(statement)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(schema)

    @staticmethod
    def _audit(conn, run_id: str, event: str, details: dict | None = None) -> None:
        conn.execute("INSERT INTO audit(run_id,created_at,event,details_json) VALUES(?,?,?,?)",
                     (run_id, time.time(), event, compact(details or {})))

    @staticmethod
    def _decode(row) -> dict | None:
        if row is None:
            return None
        result = dict(row)
        for key in list(result):
            if key.endswith("_json"):
                value = result.pop(key)
                result[key[:-5]] = json.loads(value) if value else None
        result.pop("lease_token", None)
        result.pop("event_hash", None)
        return result

    def enqueue(self, event: Event, limit: int) -> tuple[str, bool]:
        body = compact(event.model_dump(mode="json"))
        digest = hashlib.sha256(body.encode()).hexdigest()
        now = time.time()
        with self.transaction() as conn:
            existing = conn.execute("SELECT id,event_hash FROM runs WHERE event_id=?", (event.event_id,)).fetchone()
            if existing:
                if existing["event_hash"] != digest:
                    raise Conflict("Event ID was already used with a different payload")
                return existing["id"], False
            count = conn.execute("SELECT COUNT(*) FROM runs WHERE created_at>?", (now - 86400,)).fetchone()[0]
            if count >= limit:
                raise BudgetExceeded("Daily run limit reached")
            run_id = uuid.uuid4().hex
            conn.execute("""INSERT INTO runs(id,event_id,event_json,event_hash,status,created_at,updated_at,
                            available_at) VALUES(?,?,?,?,'queued',?,?,?)""",
                         (run_id, event.event_id, body, digest, now, now, now))
            self._audit(conn, run_id, "event_received")
        return run_id, True

    def list_runs(self, limit: int = 100) -> list[dict]:
        with self.transaction() as conn:
            rows = conn.execute("""SELECT id,event_json,status,stage,created_at,updated_at,version,error
                                  FROM runs ORDER BY created_at DESC LIMIT ?""", (limit,)).fetchall()
        return [self._decode(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None
            run = self._decode(row)
            run["audit"] = [self._decode(r) for r in conn.execute(
                "SELECT * FROM audit WHERE run_id=? ORDER BY id", (run_id,)).fetchall()]
            run["deliveries"] = [self._decode(r) for r in conn.execute(
                "SELECT * FROM deliveries WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()]
            run["history"] = [self._decode(r) for r in conn.execute(
                "SELECT * FROM reports WHERE run_id=? ORDER BY version", (run_id,)).fetchall()]
        return run

    def claim(self, lease_seconds: int, max_attempts: int, run_id: str | None = None) -> dict | None:
        now = time.time()
        with self.transaction() as conn:
            expired = conn.execute("""SELECT id FROM runs WHERE status='running' AND lease_until<?
                                    AND attempts>=?""", (now, max_attempts)).fetchall()
            for r in expired:
                conn.execute("UPDATE runs SET status='failed',error='Worker lease expired',updated_at=? WHERE id=?",
                             (now, r["id"]))
                self._audit(conn, r["id"], "lease_exhausted")
            row = conn.execute("""SELECT * FROM runs WHERE attempts<? AND
                ((status='queued' AND available_at<=?) OR (status='running' AND lease_until<?))
                AND (CAST(? AS TEXT) IS NULL OR id=?) ORDER BY created_at LIMIT 1""",
                (max_attempts, now, now, run_id, run_id)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            conn.execute("""UPDATE runs SET status='running',attempts=attempts+1,lease_token=?,lease_until=?,
                            updated_at=?,error=NULL WHERE id=?""", (token, now + lease_seconds, now, row["id"]))
            self._audit(conn, row["id"], "worker_claimed", {"attempt": row["attempts"] + 1})
            result = self._decode(row)
            result["lease_token"] = token
            result["attempts"] += 1
            return result

    def heartbeat(self, run_id: str, token: str, seconds: int) -> bool:
        with self.transaction() as conn:
            return conn.execute("""UPDATE runs SET lease_until=? WHERE id=? AND lease_token=?
                                    AND status='running' AND lease_until>?""",
                                (time.time() + seconds, run_id, token, time.time())).rowcount == 1

    @staticmethod
    def _owned(conn, run_id: str, token: str):
        row = conn.execute("SELECT * FROM runs WHERE id=? AND lease_token=? AND status='running' AND lease_until>?",
                           (run_id, token, time.time())).fetchone()
        if row is None:
            raise Conflict("Worker no longer owns this run")
        return row

    def checkpoint(self, run_id: str, token: str, stage: str, field: str, value: Any,
                   metadata: dict | None = None) -> None:
        if field not in {"sources_json", "research_json"}:
            raise ValueError("Unsupported checkpoint field")
        with self.transaction() as conn:
            self._owned(conn, run_id, token)
            conn.execute(f"UPDATE runs SET {field}=?,stage=?,updated_at=? WHERE id=?",
                         (compact(value), stage, time.time(), run_id))
            if metadata is not None:
                conn.execute("UPDATE runs SET messages_json=?,metrics_json=? WHERE id=?",
                             (compact(metadata["messages"]), compact(metadata["metrics"]), run_id))
            self._audit(conn, run_id, stage)

    def finish(self, run_id: str, token: str, research: dict, report: dict, messages: list,
               metrics: dict, public_url: str) -> None:
        now = time.time()
        with self.transaction() as conn:
            row = self._owned(conn, run_id, token)
            conn.execute("""UPDATE runs SET status='awaiting_approval',stage='review',report_json=?,
                messages_json=?,metrics_json=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?""",
                         (compact(report), compact(messages), compact(metrics), now, run_id))
            conn.execute("INSERT INTO reports VALUES(?,?,?,?,?,?,?)",
                         (run_id, row["version"], now, compact(research), compact(report), compact(messages),
                          compact(metrics)))
            self._audit(conn, run_id, "report_ready", {"version": row["version"]})
            self._delivery(conn, run_id, row["version"], "review_requested", {
                "event_type": "review_requested", "run_id": run_id, "version": row["version"],
                "competitor": json.loads(row["event_json"])["competitor"],
                "title": research["headline"], "review_url": f"{public_url.rstrip('/')}/?run={run_id}",
                "message": "A new brief is ready. Open the review dashboard to approve, reject, or revise.",
            })

    @staticmethod
    def _delivery(conn, run_id: str, version: int, kind: str, payload: dict) -> None:
        delivery_id = uuid.uuid4().hex
        payload["delivery_id"] = delivery_id
        now = time.time()
        conn.execute("""INSERT INTO deliveries(id,run_id,version,kind,payload_json,created_at,available_at)
                        VALUES(?,?,?,?,?,?,?)""", (delivery_id, run_id, version, kind, compact(payload), now, now))

    def fail(self, run_id: str, token: str, error: str, retryable: bool, max_attempts: int) -> None:
        with self.transaction() as conn:
            row = self._owned(conn, run_id, token)
            retry = retryable and row["attempts"] < max_attempts
            conn.execute("""UPDATE runs SET status=?,error=?,available_at=?,updated_at=?,lease_token=NULL,
                lease_until=NULL WHERE id=?""", ("queued" if retry else "failed", error,
                time.time() + min(300, 15 * 2 ** row["attempts"]), time.time(), run_id))
            self._audit(conn, run_id, "retry_scheduled" if retry else "run_failed", {"error": error})

    def review(self, run_id: str, version: int, decision: str, feedback: str, public_url: str) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["status"] != "awaiting_approval" or row["version"] != version:
                raise Conflict("The report changed or was already reviewed; refresh before reviewing")
            if decision == "revise":
                if not feedback.strip():
                    raise ValueError("Revision requires feedback")
                if version >= 2:
                    raise Conflict("One revision is allowed; approve or reject this version")
                conn.execute("""UPDATE runs SET status='queued',stage='revision',version=version+1,
                    attempts=0,report_json=NULL,feedback=?,
                    available_at=?,updated_at=? WHERE id=?""", (feedback.strip(), time.time(), time.time(), run_id))
            elif decision in {"approve", "reject"}:
                status = "approved" if decision == "approve" else "rejected"
                conn.execute("UPDATE runs SET status=?,updated_at=? WHERE id=?", (status, time.time(), run_id))
                if decision == "approve":
                    research = json.loads(row["research_json"])
                    report = json.loads(row["report_json"])
                    self._delivery(conn, run_id, version, "approved_report", {
                        "event_type": "approved_report", "run_id": run_id, "version": version,
                        "competitor": json.loads(row["event_json"])["competitor"],
                        "title": research["headline"], "summary": report["strategic_summary"],
                        "report_url": f"{public_url.rstrip('/')}/?run={run_id}",
                        "message": report["strategic_summary"], "actions": report["actions"],
                    })
            else:
                raise ValueError("Invalid review decision")
            # Pending review notifications for old versions are no longer actionable.
            conn.execute("""UPDATE deliveries SET status='cancelled' WHERE run_id=? AND version=?
                            AND kind='review_requested' AND status IN ('pending','blocked')""", (run_id, version))
            self._audit(conn, run_id, f"human_{decision}", {"version": version, "feedback": feedback})

    def retry_run(self, run_id: str) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["status"] != "failed":
                raise Conflict("Only failed runs can be retried")
            conn.execute("""UPDATE runs SET status='queued',attempts=0,error=NULL,available_at=?,updated_at=?
                            WHERE id=?""", (time.time(), time.time(), run_id))
            self._audit(conn, run_id, "human_retry")

    def cancel_run(self, run_id: str) -> None:
        """Cancel unclaimed work while retaining evidence and its audit record."""
        with self.transaction() as conn:
            row = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["status"] not in {"queued", "failed"}:
                raise Conflict("Only queued or failed runs can be cancelled")
            conn.execute("UPDATE runs SET status='cancelled',updated_at=? WHERE id=?", (time.time(), run_id))
            conn.execute("UPDATE deliveries SET status='cancelled' WHERE run_id=? AND status IN ('pending','blocked')", (run_id,))
            self._audit(conn, run_id, "human_cancel")

    def claim_delivery(self, seconds: int, configured: bool) -> dict | None:
        now = time.time()
        with self.transaction() as conn:
            # Recover dead processes even if every previous attempt exhausted the delivery budget.
            conn.execute("""UPDATE deliveries SET status='failed',error='Delivery lease expired'
                            WHERE status='sending' AND lease_until<? AND attempts>=5""", (now,))
            if not configured:
                conn.execute("""UPDATE deliveries SET status='blocked',error='Configure ZAPIER_HOOK_URL'
                              WHERE status='pending'""")
                return None
            conn.execute("UPDATE deliveries SET status='pending',error=NULL WHERE status='blocked'")
            row = conn.execute("""SELECT d.* FROM deliveries d JOIN runs r ON r.id=d.run_id
                WHERE d.attempts<5 AND d.version=r.version AND
                ((d.kind='approved_report' AND r.status='approved') OR
                 (d.kind='review_requested' AND r.status='awaiting_approval')) AND
                ((d.status='pending' AND d.available_at<=?) OR (d.status='sending' AND d.lease_until<?))
                ORDER BY d.created_at LIMIT 1""", (now, now)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            conn.execute("""UPDATE deliveries SET status='sending',attempts=attempts+1,
                            lease_token=?,lease_until=? WHERE id=?""", (token, now + seconds, row["id"]))
            result = self._decode(row)
            result["lease_token"] = token
            result["attempts"] += 1
        return result

    def delivery_result(self, item: dict, outcome: str, error: str | None, receipt: dict | None = None) -> None:
        with self.transaction() as conn:
            if outcome not in {"sent", "failed", "pending"}:
                raise ValueError("Invalid delivery outcome")
            changed = conn.execute("""UPDATE deliveries SET status=?,error=?,receipt_json=?,available_at=?,
                lease_token=NULL,lease_until=NULL WHERE id=? AND lease_token=? AND status='sending'
                AND lease_until>?""", (outcome, error, compact(receipt) if receipt else None,
                time.time() + min(600, 15 * 2 ** item["attempts"]), item["id"], item["lease_token"],
                time.time())).rowcount
            if changed:
                self._audit(conn, item["run_id"], f"delivery_{outcome}", {
                    "delivery_id": item["id"], "kind": item["kind"], "error": error,
                })

    def retry_delivery(self, delivery_id: str) -> None:
        with self.transaction() as conn:
            row = conn.execute("""SELECT d.*,r.status AS run_status,r.version AS current_version
                FROM deliveries d JOIN runs r ON r.id=d.run_id WHERE d.id=?""", (delivery_id,)).fetchone()
            if row is None:
                raise KeyError(delivery_id)
            required_status = "approved" if row["kind"] == "approved_report" else "awaiting_approval"
            if row["version"] != row["current_version"] or row["run_status"] != required_status:
                raise Conflict("This delivery is no longer authorized")
            if row["status"] not in {"failed", "blocked"}:
                raise Conflict("Only failed or blocked deliveries can be retried")
            conn.execute("""UPDATE deliveries SET status='pending',attempts=0,error=NULL,available_at=?
                            WHERE id=?""", (time.time(), delivery_id))
            self._audit(conn, row["run_id"], "delivery_replayed", {"delivery_id": delivery_id})

    def worker_seen(self, worker_id: str) -> None:
        with self.transaction() as conn:
            conn.execute("""INSERT INTO worker_health VALUES(?,?)
                            ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen""",
                         (worker_id, time.time()))

    def health(self) -> dict:
        with self.transaction() as conn:
            last = conn.execute("SELECT MAX(last_seen) FROM worker_health").fetchone()[0]
            rows = conn.execute("SELECT status,COUNT(*) AS count FROM runs GROUP BY status").fetchall()
            counts = {row["status"]: row["count"] for row in rows}
        return {"database": "ok", "worker_online": bool(last and time.time() - last < 30), "runs": counts}
