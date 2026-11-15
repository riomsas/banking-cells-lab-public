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
from app.cells import CELLS, route


class ServiceDomainRoutingTest(unittest.TestCase):
    def test_payments_digital(self):
        result = route({"synthetic": True, "channel": "digital", "amount": "75.25", "service_domain": "payments"})
        self.assertEqual(result["cell_id"], "CELL-DIGITAL-PAYMENTS-01")
        self.assertEqual(result["service_domain"], "payments")
        self.assertEqual(result["amount"], "75.25")

    def test_payments_branch(self):
        self.assertEqual(route({"synthetic": True, "channel": "branch", "amount": "10", "service_domain": "payments"})["cell_id"], "CELL-BRANCH-PAYMENTS-01")

    def test_onboarding_digital(self):
        self.assertEqual(route({"synthetic": True, "channel": "digital", "amount": "1", "service_domain": "onboarding"})["cell_id"], "CELL-DIGITAL-ONBOARDING-01")

    def test_onboarding_inactive_branch_rejected(self):
        with self.assertRaisesRegex(ValueError, "NO_ACTIVE_CELL"):
            route({"synthetic": True, "channel": "branch", "amount": "1", "service_domain": "onboarding"})

    def test_unknown_domain_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_SERVICE_DOMAIN"):
            route({"synthetic": True, "channel": "digital", "amount": "1", "service_domain": "loans"})

    def test_non_string_domain_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_SERVICE_DOMAIN"):
            route({"synthetic": True, "channel": "digital", "amount": "1", "service_domain": ["payments"]})

    def test_non_synthetic_rejected_before_routing(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_DATA_REQUIRED"):
            route({"synthetic": "true", "channel": "digital", "amount": "1", "service_domain": "payments"})

    def test_no_duplicate_cell_identity_or_domain_channel(self):
        self.assertEqual(len({cell.id for cell in CELLS}), len(CELLS))
        self.assertEqual(len({(cell.service_domain, cell.channel) for cell in CELLS}), len(CELLS))
