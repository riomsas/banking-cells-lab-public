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

"""Synthetic banking cell routing organized by bounded service domains.

This is an educational BIAN-inspired domain map, not an official BIAN taxonomy.
No external banking integration, payment execution, or persistence.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Cell:
    id: str
    channel: str
    active: bool
    service_domain: str = "general-banking"


# Explicitly bounded service-domain ownership (DDD); no shared mutable state.
CELLS = (
    Cell("CELL-DIGITAL-01", "digital", True),
    Cell("CELL-BRANCH-01", "branch", True),
    Cell("CELL-DIGITAL-PAYMENTS-01", "digital", True, "payments"),
    Cell("CELL-BRANCH-PAYMENTS-01", "branch", True, "payments"),
    Cell("CELL-DIGITAL-ONBOARDING-01", "digital", True, "onboarding"),
    Cell("CELL-BRANCH-ONBOARDING-01", "branch", False, "onboarding"),
)
SERVICE_DOMAINS = frozenset(cell.service_domain for cell in CELLS)
CHANNELS = frozenset(("digital", "branch"))


def route(request: dict) -> dict:
    """Select an active cell using only explicitly synthetic requests.

    The optional service_domain is backward compatible with pilot 001.
    """
    if not isinstance(request, dict) or request.get("synthetic") is not True:
        raise ValueError("SYNTHETIC_DATA_REQUIRED")
    channel = request.get("channel")
    if not isinstance(channel, str) or channel not in CHANNELS:
        raise ValueError("UNSUPPORTED_CHANNEL")
    domain = request.get("service_domain", "general-banking")
    if not isinstance(domain, str) or domain not in SERVICE_DOMAINS:
        raise ValueError("UNSUPPORTED_SERVICE_DOMAIN")
    try:
        amount = Decimal(str(request["amount"]))
    except (KeyError, InvalidOperation, ValueError, TypeError):
        raise ValueError("INVALID_AMOUNT") from None
    if not amount.is_finite() or amount <= 0 or amount > 10000:
        raise ValueError("AMOUNT_OUT_OF_RANGE")
    cell = next(
        (cell for cell in CELLS
         if cell.active and cell.channel == channel and cell.service_domain == domain),
        None,
    )
    if cell is None:
        raise ValueError("NO_ACTIVE_CELL")
    return {
        "cell_id": cell.id,
        "status": "ROUTED_SYNTHETIC",
        "amount": str(amount),
        "service_domain": domain,
    }
