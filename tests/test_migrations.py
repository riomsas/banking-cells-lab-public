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

import contextlib
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.cells import CELLS
from app.platform import Laboratory


class MigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup_dir, directory)
        self.path = Path(directory.name) / "lab.sqlite"

    @staticmethod
    def _cleanup_dir(directory):
        try:
            directory.cleanup()
        except OSError:
            time.sleep(0.05)
            try:
                directory.cleanup()
            except OSError:
                pass

    def open_and_count(self):
        lab = Laboratory(self.path)
        try:
            return lab.db.execute("SELECT COUNT(*) FROM cells").fetchone()[0]
        finally:
            lab.close()

    def test_concurrent_initialization(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            counts = list(pool.map(lambda _: self.open_and_count(), range(8)))
        self.assertEqual(counts, [len(CELLS)] * 8)

    def test_unversioned_database_preserves_existing_data(self):
        lab = Laboratory(self.path)
        try:
            lab.db.execute("UPDATE cells SET capacity = 17")
            lab.db.execute("PRAGMA user_version=0")
        finally:
            lab.close()
        reopened = Laboratory(self.path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.db.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual({row[0] for row in reopened.db.execute("SELECT capacity FROM cells")}, {17})

    def test_failed_initialization_rolls_back_schema_and_version(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE cells (legacy TEXT)")
        with self.assertRaises(sqlite3.OperationalError):
            Laboratory(self.path)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("cells",)])

    def test_future_schema_is_preserved(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(RuntimeError, "schema version: 2"):
            Laboratory(self.path)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
