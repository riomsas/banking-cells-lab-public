# Banking Cells Architecture Lab — Community Edition

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Data](https://img.shields.io/badge/Data-Exclusively_Synthetic-green.svg)](#scope-and-synthetic-data-disclaimer)

**Consulting RIOM S.A.S.** · Open-source reference implementation of cell-based banking architectures.

[Consulting RIOM](https://consultingriom.com/) · [Live Demonstration Showcase](https://banking-cells.consultingriom.com/)

---

## Scope and Synthetic Data Disclaimer

> **IMPORTANT:** Banking Cells Architecture Lab — Community Edition is designed strictly for architectural exploration, educational demonstration, and engineering evaluation.
>
> - It operates **exclusively with synthetic test data**.
> - It is **not connected to banking entities**, clearing houses, payment networks, or core banking platforms.
> - It **does not process real money or financial transactions**.
> - It is **not certified for production financial operations** and must not be exposed directly to untrusted public networks without enterprise security, authentication, and ingress controls.

---

## Architectural Vision

Modern financial institutions face critical scalability and availability challenges when scaling monolithic core systems. **Cell-based architecture (CBA)** isolates workloads into independent, fault-tolerant units ("cells") that encapsulate bounded contexts, domain services, channel interfaces, operational capacity, and failure domains.

This laboratory provides an executable reference implementation inspired by:
- **Domain-Driven Design (DDD):** Clean boundary contexts separating service domains (`General Banking`, `Payments`, `Onboarding`) and channels (`Digital`, `Branch`).
- **BIAN Functional Decomposition Principles:** Modular banking capabilities with explicit lifecycle contracts and deterministic routing.

---

## Functional Capabilities

| Module | Core Capability |
| ------ | --------------- |
| **Dashboard** | Real-time indicators computed from persistent state: total cells, active/inactive counts, available capacity, current load, processed/rejected requests, and utilization percentage. |
| **Cells Catalog** | Complete cell lifecycle management (`DRAFT` → `ACTIVE` ⇄ `SUSPENDED` ⇄ `INACTIVE` → `RETIRED`), capacity allocation, and priority configuration. |
| **Synthetic Routing** | Deterministic request routing matching domain, channel, active state, and available capacity with full idempotency and capacity release upon completion. |
| **Simulation** | Synthetic load scenarios (up to 100 concurrent requests per batch), measuring throughput, saturation thresholds, and allocation distributions. |
| **Analytics** | Request distribution by service domain and channel; temporal event trends per minute. |
| **Traceability Events** | Immutable audit trail tracking creation, state transitions, routing decisions, request completions, rejections, and simulation executions. |

---

## Technical Architecture

```text
       Browser Web Console (HTML5 / CSS3 / Vanilla JS)
                             │
                      HTTP REST API
                             │
             Python 3.12+ Application Core
            (app/platform.py, app/cells.py)
                             │
               SQLite Embedded Database
            (Transactional Schema Migrations)
```

- **Backend:** Pure Python 3.12+ leveraging only the standard library (`http.server`, `sqlite3`, `json`, `threading`). **Zero external runtime dependencies required.**
- **Frontend:** Modern, lightweight, accessible web console (`app/web/`) styled with responsive layout support across desktop, tablet, and mobile viewports.
- **Persistence:** SQLite with automated, atomic schema migration and validation.
- **Automated Verification:** Comprehensive test suite including unit tests, real HTTP integration tests, and Playwright end-to-end browser tests.

---

## Quickstart

### Prerequisites
- **Python 3.12 or superior** installed.
- (Optional for browser E2E tests): **Node.js 20+** and Playwright.

### 1. Run Unit and Integration Tests
```bash
python -m unittest discover -s tests -v
```

### 2. Start the Local Web Console
```bash
python -m app.api
```
The console will start at: **http://127.0.0.1:8765** (bound strictly to localhost for safety).

### 3. Persistent SQLite Storage
By default, SQLite runs in volatile in-memory mode (`:memory:`). To persist synthetic data across restarts:
```bash
# Windows PowerShell
$env:RIOM_LAB_DB = 'C:\path\to\your\data\lab.sqlite3'
python -m app.api

# Linux / macOS
export RIOM_LAB_DB='/path/to/your/data/lab.sqlite3'
python -m app.api
```

### 4. Running Browser End-to-End Tests
```bash
npm install playwright
npx playwright install chromium
node tests/browser-e2e.cjs
```

---

## Authorship and Professional Attribution

**Ricardo Vinicio Castelo Mosquera**  
*Founder & Senior Consultant · Consulting RIOM S.A.S.*  
*Enterprise Architecture, Digital Transformation & Financial Technology*

- Computer Systems Engineer; Master in Information Technology with mention in Digital Transformation and Innovation; Master in Agile Project Management and Digital Transformation.
- Over 16 years of hands-on leadership in the financial sector, specializing in banking core architecture, digital channels, payment switches, digital strategies, and enterprise innovation.
- Professional experience includes engineering and executive leadership roles across major financial institutions including **CACPECO, Banco del Austro, Banco Pichincha, and Mutualista Pichincha**.

**LinkedIn:** [Ricardo Castelo Mosquera](https://www.linkedin.com/in/ricardocastelom/)  
**Organization:** [Consulting RIOM S.A.S.](https://consultingriom.com/) · [Company LinkedIn](https://www.linkedin.com/company/consulting-riom)

---

## License and Intellectual Property

### Open Source License
Banking Cells Architecture Lab — Community Edition is licensed under the **[Apache License, Version 2.0](LICENSE)**.

### Proprietary Framework Notice
Proprietary Consulting RIOM S.A.S. software, internal tooling and non-distributed materials are excluded from this Community Edition. The Apache License 2.0 applies only to the files published in this repository.

### Trademarks and Brand Assets
The names **"RIOM"**, **"Consulting RIOM"**, and associated corporate logos and wordmarks are proprietary trademarks of Consulting RIOM S.A.S. In accordance with Section 6 of the Apache License 2.0, this license does not grant permission to use the trade names or trademarks of the Licensor for commercial or derivative branding without prior written authorization. See [NOTICE](NOTICE) for full details.
