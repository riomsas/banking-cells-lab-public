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

import unittest
from app.cells import route

class CellsTest(unittest.TestCase):
    def test_digital(self):
        self.assertEqual(route({"synthetic": True, "channel": "digital", "amount": "125.00"})["cell_id"], "CELL-DIGITAL-01")
    def test_branch(self):
        self.assertEqual(route({"synthetic": True, "channel": "branch", "amount": "1"})["cell_id"], "CELL-BRANCH-01")
    def test_real_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_DATA_REQUIRED"):
            route({"channel": "digital", "amount": "1"})
    def test_invalid_channel(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_CHANNEL"):
            route({"synthetic": True, "channel": "atm", "amount": "1"})
    def test_invalid_amount(self):
        for amount in ("nan", "infinity", "0", "-1", "10001", "abc"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                route({"synthetic": True, "channel": "digital", "amount": amount})
