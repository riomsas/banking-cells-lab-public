# Copyright 2026 Consulting RIOM S.A.S.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Local-only synthetic banking cell service with SQLite-backed lifecycle and routing.

This module does not connect to banks and is not an official BIAN implementation.
It reuses the existing app.cells catalog as safe seed data.
"""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from .cells import CELLS, CHANNELS, SERVICE_DOMAINS

STATES = ("DRAFT", "ACTIVE", "SUSPENDED", "INACTIVE", "RETIRED")
TRANSITIONS = {
    "DRAFT": {"ACTIVE", "INACTIVE"},
    "ACTIVE": {"SUSPENDED", "INACTIVE"},
    "SUSPENDED": {"ACTIVE", "INACTIVE"},
    "INACTIVE": {"ACTIVE", "RETIRED"},
    "RETIRED": set(),
}


class DomainError(ValueError):
    def __init__(self, code, status=422):
        super().__init__(code)
        self.code, self.status = code, status


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_amount(value):
    if isinstance(value, bool):
        raise DomainError("INVALID_AMOUNT")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError("INVALID_AMOUNT") from None
    if not amount.is_finite() or not 0 < amount <= 10000:
        raise DomainError("AMOUNT_OUT_OF_RANGE")
    return str(amount)


def positive_int(value, key, maximum=10000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise DomainError("INVALID_" + key.upper())
    return value


class Laboratory:
    def __init__(self, database=":memory:"):
        self.db = sqlite3.connect(str(database), isolation_level=None, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        try:
            self._migrate()
        except Exception:
            self.close()
            raise

    def _migrate(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                self._initialize_v1()
                self.db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise RuntimeError(f"Unsupported SQLite schema version: {version}")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _initialize_v1(self):
        schema = """
        CREATE TABLE IF NOT EXISTS cells (
          id TEXT PRIMARY KEY, domain TEXT NOT NULL, channel TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('DRAFT','ACTIVE','SUSPENDED','INACTIVE','RETIRED')),
          capacity INTEGER NOT NULL CHECK(capacity > 0), used INTEGER NOT NULL DEFAULT 0
          CHECK(used >= 0 AND used <= capacity),
          priority INTEGER NOT NULL DEFAULT 100 CHECK(priority BETWEEN 1 AND 1000),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS requests (
          id TEXT PRIMARY KEY, cell_id TEXT REFERENCES cells(id),
          domain TEXT NOT NULL, channel TEXT NOT NULL, amount TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('ROUTED','COMPLETED')),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, type TEXT NOT NULL,
          cell_id TEXT, request_id TEXT, detail TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_at ON events(id DESC);
        CREATE TABLE IF NOT EXISTS simulations (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, domain TEXT NOT NULL,
          channel TEXT NOT NULL, requested INTEGER NOT NULL,
          routed INTEGER NOT NULL, rejected INTEGER NOT NULL, by_cell TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_simulations_created_at ON simulations(created_at DESC);
        """
        for statement in schema.strip().rstrip(";").split(";"):
            self.db.execute(statement)
        if self.db.execute("SELECT COUNT(*) FROM cells").fetchone()[0] == 0:
            for cell in CELLS:
                self.db.execute(
                    "INSERT INTO cells(id, domain, channel, state, capacity, created_at) VALUES (?,?,?,?,?,?)",
                    (cell.id, cell.service_domain, cell.channel, "ACTIVE" if cell.active else "INACTIVE", 10, stamp()),
                )

    def close(self):
        self.db.close()

    def _event(self, kind, cell_id=None, request_id=None, detail=None):
        self.db.execute(
            "INSERT INTO events(at,type,cell_id,request_id,detail) VALUES(?,?,?,?,?)",
            (stamp(), kind, cell_id, request_id, json.dumps(detail or {}, sort_keys=True)),
        )

    def _cell(self, cell_id):
        row = self.db.execute("SELECT * FROM cells WHERE id=?", (cell_id,)).fetchone()
        if row is None:
            raise DomainError("CELL_NOT_FOUND", 404)
        return dict(row)

    def cells(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM cells ORDER BY domain,channel,priority,id")]

    def create_cell(self, body):
        if not isinstance(body, dict) or body.get("synthetic") is not True:
            raise DomainError("SYNTHETIC_DATA_REQUIRED")
        cell_id, domain, channel = body.get("id"), body.get("service_domain"), body.get("channel")
        if not isinstance(cell_id, str) or not 1 <= len(cell_id) <= 60 or not all(c.isascii() and (c.isalnum() or c == "-") for c in cell_id):
            raise DomainError("INVALID_CELL_ID")
        if domain not in SERVICE_DOMAINS or channel not in CHANNELS:
            raise DomainError("UNSUPPORTED_DOMAIN_OR_CHANNEL")
        capacity = positive_int(body.get("capacity"), "capacity")
        priority = positive_int(body.get("priority", 100), "priority", 1000)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            try:
                self.db.execute(
                    "INSERT INTO cells(id,domain,channel,state,capacity,priority,created_at) VALUES(?,?,?,?,?,?,?)",
                    (cell_id, domain, channel, "DRAFT", capacity, priority, stamp()),
                )
            except sqlite3.IntegrityError:
                raise DomainError("CELL_ALREADY_EXISTS", 409) from None
            self._event("CELL_CREATED", cell_id, detail={"state": "DRAFT"})
            cell = self._cell(cell_id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return cell

    def transition(self, cell_id, new_state, reason):
        if new_state not in STATES:
            raise DomainError("INVALID_STATE")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
            raise DomainError("REASON_REQUIRED")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cell = self._cell(cell_id)
            if new_state not in TRANSITIONS[cell["state"]]:
                raise DomainError("INVALID_TRANSITION", 409)
            if cell["used"] and new_state != "ACTIVE":
                raise DomainError("CELL_HAS_ACTIVE_REQUESTS", 409)
            self.db.execute("UPDATE cells SET state=? WHERE id=?", (new_state, cell_id))
            self._event("STATE_CHANGED", cell_id, detail={"from": cell["state"], "to": new_state, "reason": reason.strip()})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return self._cell(cell_id)

    def set_capacity(self, cell_id, capacity, priority=None):
        capacity = positive_int(capacity, "capacity")
        if priority is not None:
            priority = positive_int(priority, "priority", 1000)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cell = self._cell(cell_id)
            if cell["state"] == "RETIRED" or capacity < cell["used"]:
                raise DomainError("CAPACITY_CHANGE_REJECTED", 409)
            self.db.execute("UPDATE cells SET capacity=?,priority=? WHERE id=?",
                            (capacity, cell["priority"] if priority is None else priority, cell_id))
            self._event("CAPACITY_CHANGED", cell_id, detail={"capacity": capacity})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return self._cell(cell_id)

    def route(self, request):
        if not isinstance(request, dict) or request.get("synthetic") is not True:
            raise DomainError("SYNTHETIC_DATA_REQUIRED")
        domain = request.get("service_domain", "general-banking")
        channel = request.get("channel")
        if not isinstance(domain, str) or domain not in SERVICE_DOMAINS:
            raise DomainError("UNSUPPORTED_SERVICE_DOMAIN")
        if not isinstance(channel, str) or channel not in CHANNELS:
            raise DomainError("UNSUPPORTED_CHANNEL")
        if "amount" not in request:
            raise DomainError("INVALID_AMOUNT")
        amount = validate_amount(request["amount"])
        request_id = request.get("request_id") or "SYN-" + uuid4().hex[:16]
        if not isinstance(request_id, str) or not request_id.startswith("SYN-") or len(request_id) > 60:
            raise DomainError("INVALID_REQUEST_ID")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior is not None:
                if (prior["domain"], prior["channel"], prior["amount"]) != (domain, channel, amount):
                    raise DomainError("IDEMPOTENCY_CONFLICT", 409)
                result = {"request_id": request_id, "cell_id": prior["cell_id"],
                          "status": prior["status"], "idempotent": True}
                self.db.execute("COMMIT")
                return result
            row = self.db.execute(
                """SELECT * FROM cells WHERE domain=? AND channel=? AND state='ACTIVE'
                AND used < capacity ORDER BY priority ASC, used * 1.0 / capacity ASC, id ASC LIMIT 1""",
                (domain, channel),
            ).fetchone()
            if row is None:
                active_cell = self.db.execute(
                    "SELECT 1 FROM cells WHERE domain=? AND channel=? AND state='ACTIVE' LIMIT 1",
                    (domain, channel),
                ).fetchone()
                self._event("REQUEST_REJECTED", request_id=request_id, detail={
                    "domain": domain, "channel": channel, "reason": "NO_CAPACITY",
                    "cause": "SATURATED" if active_cell else "NO_ACTIVE_CELL",
                })
                self.db.execute("COMMIT")
                raise DomainError("NO_ELIGIBLE_CELL", 409)
            self.db.execute("UPDATE cells SET used=used+1 WHERE id=?", (row["id"],))
            self.db.execute(
                "INSERT INTO requests(id,cell_id,domain,channel,amount,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (request_id, row["id"], domain, channel, amount, "ROUTED", stamp()),
            )
            self._event("REQUEST_ROUTED", row["id"], request_id, {"domain": domain, "channel": channel})
            self.db.execute("COMMIT")
            return {"request_id": request_id, "cell_id": row["id"], "status": "ROUTED", "idempotent": False}
        except DomainError as ex:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise ex
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def complete(self, request_id):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise DomainError("REQUEST_NOT_FOUND", 404)
            if row["status"] == "COMPLETED":
                self.db.execute("COMMIT")
                return {"request_id": request_id, "status": "COMPLETED", "idempotent": True}
            self.db.execute("UPDATE requests SET status='COMPLETED' WHERE id=?", (request_id,))
            self.db.execute("UPDATE cells SET used=used-1 WHERE id=? AND used>0", (row["cell_id"],))
            self._event("REQUEST_COMPLETED", row["cell_id"], request_id)
            self.db.execute("COMMIT")
            return {"request_id": request_id, "status": "COMPLETED", "idempotent": False}
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def events(self, limit=100):
        limit = positive_int(limit, "limit", 500)
        return [{**dict(row), "detail": json.loads(row["detail"])}
                for row in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def metrics(self):
        cells = self.cells()
        total = sum(c["capacity"] for c in cells if c["state"] == "ACTIVE")
        used = sum(c["used"] for c in cells)
        accepted = self.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        rejected = self.db.execute("SELECT COUNT(*) FROM events WHERE type='REQUEST_REJECTED'").fetchone()[0]
        return {
            "synthetic": True, "cells_total": len(cells),
            "cells_active": sum(c["state"] == "ACTIVE" for c in cells),
            "cells_inactive": sum(c["state"] != "ACTIVE" for c in cells),
            "capacity_total": total, "capacity_used": used,
            "capacity_available": max(0, total - used),
            "utilization_percent": round(100 * used / total, 2) if total else 0,
            "requests_processed": accepted, "requests_rejected": rejected,
            "rejection_percent": round(100 * rejected / (accepted + rejected), 2) if accepted + rejected else 0,
        }

    def analytics(self):
        """Operational analytics derived from synthetic records and event timestamps."""
        counts = self.db.execute(
            "SELECT domain,channel,COUNT(*) AS requests FROM requests GROUP BY domain,channel ORDER BY domain,channel"
        ).fetchall()
        trend = self.db.execute(
            """SELECT substr(at,1,16) AS minute, type, COUNT(*) AS count FROM events
               WHERE type IN ('REQUEST_ROUTED','REQUEST_REJECTED','REQUEST_COMPLETED')
               GROUP BY minute,type ORDER BY minute,type"""
        ).fetchall()
        distribution = self.db.execute(
            """SELECT domain,channel,state,COUNT(*) AS cells,SUM(capacity) AS capacity,
                      SUM(used) AS used FROM cells GROUP BY domain,channel,state
               ORDER BY domain,channel,state"""
        ).fetchall()
        return {"synthetic": True, "requests_by_domain_channel": [dict(r) for r in counts],
                "event_trend": [dict(r) for r in trend],
                "cell_distribution": [dict(r) for r in distribution]}

    def simulations(self, limit=20):
        limit = positive_int(limit, "limit", 100)
        return [{**dict(row), "by_cell": json.loads(row["by_cell"])}
                for row in self.db.execute(
                    "SELECT * FROM simulations ORDER BY created_at DESC,id DESC LIMIT ?", (limit,))]

    def simulate(self, body):
        if not isinstance(body, dict) or body.get("synthetic") is not True:
            raise DomainError("SYNTHETIC_DATA_REQUIRED")
        count = positive_int(body.get("count"), "count", 100)
        channel = body.get("channel")
        domain = body.get("service_domain", "general-banking")
        if channel not in CHANNELS or domain not in SERVICE_DOMAINS:
            raise DomainError("UNSUPPORTED_DOMAIN_OR_CHANNEL")
        routed, rejected = [], 0
        for _ in range(count):
            try:
                routed.append(self.route({"synthetic": True, "channel": channel,
                                          "service_domain": domain, "amount": "1"}))
            except DomainError as ex:
                if ex.code != "NO_ELIGIBLE_CELL":
                    raise
                rejected += 1
        distribution = {
            cid: sum(r["cell_id"] == cid for r in routed)
            for cid in sorted({r["cell_id"] for r in routed})
        }
        simulation_id = "SIM-" + uuid4().hex[:16]
        # Keep the scenario summary and its audit event consistent.
        # Individual routing decisions remain committed by route() above.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO simulations(id,created_at,domain,channel,requested,routed,rejected,by_cell) VALUES(?,?,?,?,?,?,?,?)",
                (simulation_id, stamp(), domain, channel, count, len(routed), rejected,
                 json.dumps(distribution, sort_keys=True)),
            )
            self._event("SIMULATION_COMPLETED", detail={"simulation_id": simulation_id})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"synthetic": True, "simulation_id": simulation_id, "requested": count,
                "routed": len(routed), "rejected": rejected, "by_cell": distribution}
