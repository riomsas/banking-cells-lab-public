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

"""Integration coverage: isolated in-memory SQLite and local HTTP API."""
import http.client
import json
from unittest.mock import patch
import threading
import unittest
from http.server import HTTPServer

from app.platform import DomainError, Laboratory
from app.api import handler_factory


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.lab = Laboratory()

    def tearDown(self):
        self.lab.close()

    def test_seed_and_metrics(self):
        self.assertEqual(len(self.lab.cells()), 6)
        self.assertEqual(self.lab.metrics()["cells_active"], 5)
        self.assertEqual(self.lab.metrics()["capacity_available"], 50)

    def test_create_activate_suspend_retire(self):
        cell = self.lab.create_cell({"synthetic": True, "id": "SYN-CELL-7", "service_domain": "payments",
                                     "channel": "digital", "capacity": 2})
        self.assertEqual(cell["state"], "DRAFT")
        self.lab.transition("SYN-CELL-7", "ACTIVE", "Test")
        self.lab.transition("SYN-CELL-7", "INACTIVE", "Test")
        self.lab.transition("SYN-CELL-7", "RETIRED", "Test")
        with self.assertRaisesRegex(DomainError, "INVALID_TRANSITION"):
            self.lab.transition("SYN-CELL-7", "ACTIVE", "Test")
        self.assertTrue(any(e["type"] == "STATE_CHANGED" for e in self.lab.events()))

    def test_cell_creation_rolls_back_when_audit_write_fails(self):
        payload = {"synthetic": True, "id": "SYN-ROLLBACK", "service_domain": "payments",
                   "channel": "digital", "capacity": 2}
        with patch.object(self.lab, "_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.lab.create_cell(payload)
        with self.assertRaisesRegex(DomainError, "CELL_NOT_FOUND"):
            self.lab._cell(payload["id"])
        self.assertEqual(self.lab.create_cell(payload)["state"], "DRAFT")
        self.assertEqual(sum(e["cell_id"] == payload["id"] for e in self.lab.events()), 1)

    def test_capacity_and_idempotency(self):
        self.lab.set_capacity("CELL-DIGITAL-01", 1)
        request = {"synthetic": True, "channel": "digital", "amount": "4",
                   "request_id": "SYN-SAME"}
        result = self.lab.route(request)
        self.assertEqual(result["cell_id"], "CELL-DIGITAL-01")
        self.assertTrue(self.lab.route(request)["idempotent"])
        with self.assertRaisesRegex(DomainError, "IDEMPOTENCY_CONFLICT"):
            self.lab.route({**request, "amount": "5"})
        with self.assertRaisesRegex(DomainError, "NO_ELIGIBLE_CELL"):
            self.lab.route({**request, "request_id": "SYN-OTHER"})
        self.assertEqual(self.lab.metrics()["requests_rejected"], 1)
        with self.assertRaisesRegex(DomainError, "INVALID_CAPACITY"):
            self.lab.set_capacity("CELL-DIGITAL-01", 0)
        self.assertFalse(self.lab.complete("SYN-SAME")["idempotent"])
        self.assertTrue(self.lab.complete("SYN-SAME")["idempotent"])
        self.assertEqual(self.lab.metrics()["capacity_used"], 0)

    def test_no_inactive_or_retired_assignment(self):
        with self.assertRaisesRegex(DomainError, "NO_ELIGIBLE_CELL"):
            self.lab.route({"synthetic": True, "channel": "branch",
                            "service_domain": "onboarding", "amount": "1"})

    def test_routing_rejection_records_request_and_cause(self):
        request = {"synthetic": True, "channel": "digital", "amount": "1"}
        self.lab.set_capacity("CELL-DIGITAL-01", 1)
        self.lab.route({**request, "request_id": "SYN-FILL"})
        for request_id, options, cause in (
            ("SYN-SATURATED", {}, "SATURATED"),
            ("SYN-NO-ACTIVE", {"channel": "branch", "service_domain": "onboarding"}, "NO_ACTIVE_CELL"),
        ):
            with self.subTest(cause=cause):
                with self.assertRaisesRegex(DomainError, "NO_ELIGIBLE_CELL"):
                    self.lab.route({**request, **options, "request_id": request_id})
                event = self.lab.events()[0]
                self.assertEqual(event["type"], "REQUEST_REJECTED")
                self.assertEqual(event["request_id"], request_id)
                self.assertEqual(event["detail"]["cause"], cause)

    def test_invalid_requests(self):
        for payload in [{}, {"synthetic": "true", "id": "x"}, {"synthetic": True, "id": "a/b",
                        "service_domain": "payments", "channel": "digital", "capacity": 5}]:
            with self.subTest(payload=payload), self.assertRaises(DomainError):
                self.lab.create_cell(payload)
        for invalid in ("nan", "-1", "infinity", 0, True):
            with self.subTest(amount=invalid), self.assertRaises(DomainError):
                self.lab.route({"synthetic": True, "channel": "digital", "amount": invalid})

    def test_simulation_metrics_events(self):
        result = self.lab.simulate({"synthetic": True, "count": 12,
                                    "channel": "digital", "service_domain": "payments"})
        self.assertEqual((result["routed"], result["rejected"]), (10, 2))
        self.assertEqual(self.lab.metrics()["requests_processed"], 10)
        self.assertEqual(self.lab.metrics()["requests_rejected"], 2)
        self.assertTrue(any(e["type"] == "REQUEST_REJECTED" for e in self.lab.events()))
        self.assertTrue(result["simulation_id"].startswith("SIM-"))
        self.assertEqual(self.lab.simulations()[0]["routed"], 10)
        self.assertIn("requests_by_domain_channel", self.lab.analytics())
        self.assertGreaterEqual(len(self.lab.analytics()["event_trend"]), 1)

    def test_simulation_summary_rolls_back_when_completion_audit_fails(self):
        """No scenario record may be published without its completion audit."""
        def fail_completion_event(kind, *args, **kwargs):
            if kind == "SIMULATION_COMPLETED":
                raise RuntimeError("audit unavailable")
            return original_event(kind, *args, **kwargs)

        original_event = self.lab._event
        with patch.object(self.lab, "_event", side_effect=fail_completion_event):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.lab.simulate({"synthetic": True, "count": 2,
                                   "channel": "digital", "service_domain": "payments"})
        self.assertEqual(self.lab.simulations(), [])
        self.assertEqual(
            sum(event["type"] == "SIMULATION_COMPLETED" for event in self.lab.events()), 0
        )
        # Routing decisions were already committed independently; don't
        # misrepresent a completed scenario as an atomic whole-lot operation.
        self.assertEqual(self.lab.metrics()["requests_processed"], 2)
        self.assertEqual(self.lab.metrics()["capacity_used"], 2)
        self.assertFalse(self.lab.db.in_transaction)
        self.assertEqual(
            self.lab.simulate({"synthetic": True, "count": 1,
                               "channel": "digital", "service_domain": "payments"})["routed"], 1
        )

    def test_active_request_blocks_suspend(self):
        self.lab.route({"synthetic": True, "channel": "digital", "amount": 1})
        with self.assertRaisesRegex(DomainError, "CELL_HAS_ACTIVE_REQUESTS"):
            self.lab.transition("CELL-DIGITAL-01", "SUSPENDED", "Maintenance")

    def test_unique_cell_id(self):
        payload = {"synthetic": True, "id": "SYN-NEW", "service_domain": "payments",
                   "channel": "branch", "capacity": 3}
        self.lab.create_cell(payload)
        with self.assertRaisesRegex(DomainError, "CELL_ALREADY_EXISTS"):
            self.lab.create_cell(payload)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = Laboratory()
        cls.server = HTTPServer(("127.0.0.1", 0), handler_factory(cls.lab))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.lab.close()

    def call(self, method, path, payload=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        headers = {"Content-Type": "application/json"} if data is not None else {}
        c.request(method, path, body=data, headers=headers)
        response = c.getresponse()
        result = response.read()
        status, ct = response.status, response.getheader("Content-Type")
        c.close()
        return status, json.loads(result) if "application/json" in ct else result

    def test_health_domains_cells_metrics(self):
        for route in ("/api/health", "/api/domains", "/api/cells", "/api/metrics", "/api/events", "/api/analytics", "/api/simulations"):
            with self.subTest(route=route):
                self.assertEqual(self.call("GET", route)[0], 200)

    def test_api_rejects_real_payload(self):
        code, data = self.call("POST", "/api/routing", {"channel": "digital", "amount": 1})
        self.assertEqual(code, 422)
        self.assertEqual(data["error"], "SYNTHETIC_DATA_REQUIRED")

    def test_api_invalid_json(self):
        code, data = self.call("POST", "/api/routing", raw=b"{not-json}")
        self.assertEqual((code, data["error"]), (400, "INVALID_JSON"))

    def test_api_routing_completion(self):
        status, result = self.call("POST", "/api/routing", {"synthetic": True, "channel": "branch", "amount": "5"})
        self.assertEqual(status, 201)
        self.assertEqual(self.call("POST", "/api/requests/" + result["request_id"] + "/complete", {})[0], 200)

    def test_simulation_api_history(self):
        status, result = self.call("POST", "/api/simulations",
                                   {"synthetic": True, "count": 2,
                                    "channel": "digital", "service_domain": "onboarding"})
        self.assertEqual(status, 200)
        self.assertEqual(result["routed"], 2)
        status, history = self.call("GET", "/api/simulations")
        self.assertEqual(status, 200)
        self.assertIn(result["simulation_id"], {item["id"] for item in history})

    def test_non_object_json(self):
        status, data = self.call("POST", "/api/cells", raw=b"[]")
        self.assertEqual((status, data["error"]), (400, "INVALID_JSON_OBJECT"))

    def test_frontend_available(self):
        status, html = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Banking Cells", html)
        self.assertEqual(self.call("GET", "/app.js")[0], 200)


if __name__ == "__main__":
    unittest.main()
