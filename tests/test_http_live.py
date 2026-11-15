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

"""Black-box HTTP checks against a real subprocess, with isolated SQLite."""
import concurrent.futures
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class RealServerE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="riom-http-")
        cls.database = str(Path(cls.tmp.name) / "lab.sqlite3")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.process = None
        cls._start()

    @classmethod
    def _start(cls):
        env = {**os.environ, "RIOM_LAB_DB": cls.database, "RIOM_LAB_PORT": str(cls.port)}
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "app.api"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError("SERVER_STARTUP_FAILED: " + cls.process.stderr.read().decode()[-1000:])
            try:
                status, _, _, _ = cls.call("GET", "/api/health")
                if status == 200:
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.05)
        raise RuntimeError("SERVER_STARTUP_TIMEOUT")

    @classmethod
    def tearDownClass(cls):
        cls._stop()
        try:
            cls.tmp.cleanup()
        except OSError:
            time.sleep(0.1)
            try:
                cls.tmp.cleanup()
            except OSError:
                pass

    @classmethod
    def _stop(cls):
        if cls.process and cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=3)
        if cls.process:
            cls.process.stderr.close()
            cls.process = None

    @classmethod
    def call(cls, method, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(cls.base + path, data=data, method=method,
            headers=headers or ({"Content-Type": "application/json"} if data is not None else {}))
        start = time.perf_counter()
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as err:
            response = err
        with response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            status = response.status
        elapsed_ms = (time.perf_counter() - start) * 1000
        return status, content_type, json.loads(raw) if "application/json" in content_type else raw, elapsed_ms

    def test_01_all_get_endpoints_content_types(self):
        routes = (
            ("/", "text/html"),
            ("/app.js", "text/javascript"),
            ("/app.css", "text/css"),
            ("/api/health", "application/json"),
            ("/api/domains", "application/json"),
            ("/api/cells", "application/json"),
            ("/api/metrics", "application/json"),
            ("/api/events", "application/json"),
            ("/api/analytics", "application/json"),
            ("/api/simulations", "application/json"),
            ("/favicon.svg", "image/svg+xml"),
        )
        for path, expected in routes:
            with self.subTest(endpoint=path):
                status, mime, data, elapsed = self.call("GET", path)
                self.assertEqual(status, 200)
                self.assertIn(expected, mime)
                self.assertLess(elapsed, 5000)
                self.assertTrue(data is not None)

        # Prohibit directory traversal and access to unauthorized resources
        for blocked_path in ("/app.py", "/platform.py", "/../lab.sqlite3", "/assets/brand/../../api.py", "/unknown.file", "/favicon.ico", "/assets/brand/not-distributed.svg", "/assets/brand/not-distributed.png"):
            with self.subTest(blocked_path=blocked_path):
                status, _, _, _ = self.call("GET", blocked_path)
                self.assertEqual(status, 404)

    def test_02_full_lifecycle_and_routing_over_http(self):
        name = "SYN-HTTP-CELL-31"
        create = {"id": name, "service_domain": "payments", "channel": "digital",
                  "capacity": 2, "priority": 1, "synthetic": True}
        self.assertEqual(self.call("POST", "/api/cells", create)[0], 201)
        self.assertEqual(self.call("GET", "/api/cells/" + name)[2]["state"], "DRAFT")
        status, _, active, _ = self.call("POST", "/api/cells/" + name + "/transition",
                                        {"state": "ACTIVE", "reason": "Synthetic lifecycle test"})
        self.assertEqual((status, active["state"]), (200, "ACTIVE"))
        self.assertEqual(self.call("POST", "/api/cells/" + name + "/capacity", {"capacity": 1})[0], 200)
        routed = self.call("POST", "/api/routing", {
            "synthetic": True, "service_domain": "payments", "channel": "digital",
            "amount": "7.00", "request_id": "SYN-HTTP-E2E-31"})[2]
        self.assertEqual(routed["cell_id"], name)
        self.assertEqual(self.call("GET", "/api/cells/" + name)[2]["used"], 1)
        self.assertEqual(self.call("POST", "/api/routing", {
            "synthetic": True, "service_domain": "payments", "channel": "digital",
            "amount": "7.00", "request_id": "SYN-HTTP-E2E-31"})[2]["idempotent"], True)
        self.assertEqual(self.call("POST", "/api/requests/SYN-HTTP-E2E-31/complete", {})[0], 200)
        self.assertEqual(self.call("GET", "/api/cells/" + name)[2]["used"], 0)
        self.assertEqual(self.call("POST", "/api/cells/" + name + "/transition",
                                   {"state": "SUSPENDED", "reason": "Simulation"})[2]["state"], "SUSPENDED")
        self.assertEqual(self.call("POST", "/api/cells/" + name + "/transition",
                                   {"state": "INACTIVE", "reason": "Withdraw"})[2]["state"], "INACTIVE")
        self.assertEqual(self.call("POST", "/api/cells/" + name + "/transition",
                                   {"state": "RETIRED", "reason": "Withdraw"})[2]["state"], "RETIRED")
        self.assertEqual(self.call("POST", "/api/cells/" + name + "/transition",
                                   {"state": "ACTIVE", "reason": "Invalid"})[0], 409)

    def test_03_simulation_analytics_and_errors(self):
        status, _, result, _ = self.call("POST", "/api/simulations", {
            "synthetic": True, "count": 13, "service_domain": "onboarding", "channel": "digital"})
        self.assertEqual(status, 200)
        self.assertEqual(result["requested"], 13)
        self.assertEqual(result["routed"] + result["rejected"], 13)
        self.assertIn(result["simulation_id"], {r["id"] for r in self.call("GET", "/api/simulations")[2]})
        self.assertGreater(len(self.call("GET", "/api/events")[2]), 0)
        self.assertIn("event_trend", self.call("GET", "/api/analytics")[2])
        self.assertGreaterEqual(self.call("GET", "/api/metrics")[2]["requests_processed"], 1)
        self.assertEqual(self.call("POST", "/api/routing", {"channel": "digital", "amount": 1})[0], 422)
        self.assertEqual(self.call("POST", "/api/routing", {"synthetic": True,
            "channel": "unknown", "amount": 1})[0], 422)
        self.assertEqual(self.call("POST", "/api/cells", {"synthetic": False})[0], 422)
        self.assertEqual(self.call("GET", "/api/cells/nonexistent")[0], 404)
        self.assertEqual(self.call("GET", "/api/events?limit=0")[0], 422)
        self.assertEqual(self.call("POST", "/api/routing", [], {"Content-Type": "text/plain"})[0], 415)

    def test_04_sqlite_reopen_and_integrity(self):
        before = self.call("GET", "/api/cells")[2]
        self._stop()
        self._start()
        after = self.call("GET", "/api/cells")[2]
        self.assertEqual(before, after)
        self.assertEqual(self.call("GET", "/api/metrics")[2]["synthetic"], True)
        import sqlite3
        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
        finally:
            connection.close()

    def test_05_concurrent_http_requests_no_server_errors(self):
        def hit(i):
            return self.call("GET", "/api/metrics")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(hit, range(24)))
        self.assertTrue(all(r[0] == 200 for r in results))
        values = sorted(round(r[3], 2) for r in results)
        print(f"HTTP_MEASURED_24_REQUESTS_MS min={values[0]} median={values[len(values)//2]} max={values[-1]}")


if __name__ == "__main__":
    unittest.main()
