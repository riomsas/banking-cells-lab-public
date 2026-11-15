/*
 * Copyright 2026 Consulting RIOM S.A.S.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

"use strict";
// Runs an actual headless Chromium browser against the loopback Python server.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const base = process.env.RIOM_E2E_URL || "http://127.0.0.1:8765";
  let checks = 0;
  try {
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1366, height: 768 },
      { width: 768, height: 1024 },
      { width: 390, height: 844 }
    ]) {
      const page = await browser.newPage({ viewport, reducedMotion: "reduce" });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", msg => { if (msg.type() === "error") errors.push(msg.text()); });
      page.on("response", response => {
        if (response.status() >= 500) errors.push("HTTP_" + response.status() + " " + response.url());
      });
      await page.goto(base + "/", { waitUntil: "networkidle" });
      await page.locator("#notice").getByText("Datos sintéticos actualizados").waitFor();
      assert.match(await page.title(), /Banking Cells Architecture Lab/);
      assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector("header")).backgroundColor), "rgb(25, 44, 76)", "Same-origin CSS must load under CSP");
      checks++;
      assert.equal(await page.locator("#kpis article").count(), 8);
      assert.ok((await page.locator("#cells-body tr").count()) >= 6);
      if (viewport.width === 1440) {
        assert.equal(await page.locator("#events-body tr").count(), 0);
        assert.equal(await page.locator("#scenarios-body tr").count(), 0);
      }
      checks += 4;

      // Community Edition presents neutral identity without redistributing RIOM brand assets.
      const badge = page.locator("header .brand-badge");
      assert.equal(await badge.count(), 1, "Community badge must be present in header");
      const badgeBg = await page.evaluate(() => getComputedStyle(document.querySelector(".brand-badge")).backgroundColor);
      assert.equal(badgeBg, "rgb(255, 255, 255)", "Community badge must have high contrast");

      const communityIdentity = page.locator("header .brand-logo");
      assert.equal(await communityIdentity.count(), 1);
      assert.equal((await communityIdentity.innerText()).trim(), "BC LAB");
      assert.equal(await page.locator('header img[src*="riom"]').count(), 0, "No proprietary RIOM logo may be distributed");

      const faviconLink = page.locator('link[rel="icon"]');
      assert.equal(await faviconLink.count(), 1);
      assert.equal(await faviconLink.getAttribute("href"), "/favicon.svg");
      const faviconResponse = await page.evaluate(async () => {
        const res = await fetch("/favicon.svg");
        return { status: res.status, contentType: res.headers.get("Content-Type") };
      });
      assert.equal(faviconResponse.status, 200, "Neutral favicon must be served");
      assert.ok(faviconResponse.contentType.includes("image/svg+xml"));
      checks += 6;

      // Presentation labels must be consistent with form options (Capitalized Domains, Spanish Channels and States),
      // while API identifiers remain backward-compatible lowercase/raw.
      const branchDistribution = page.locator("#distribution tr").filter({ hasText: "General Banking" })
        .filter({ has: page.locator("td:nth-child(2)", { hasText: "Sucursal" }) });
      assert.equal(await branchDistribution.count(), 1);

      const branchCell = page.locator("#cells-body tr").filter({ hasText: "CELL-BRANCH-01" });
      assert.equal(await branchCell.locator("td").nth(1).innerText(), "General Banking");
      assert.equal(await branchCell.locator("td").nth(2).innerText(), "Sucursal");
      assert.equal(await branchCell.locator("td").nth(3).innerText(), "Activa");

      assert.equal(await page.locator('#create-cell select[name="channel"] option[value="branch"]').innerText(), "Sucursal");
      assert.equal(await page.locator('#create-cell select[name="service_domain"] option[value="general-banking"]').innerText(), "General Banking");
      assert.equal(await page.locator('#create-cell select[name="service_domain"] option[value="payments"]').innerText(), "Payments");
      assert.equal(await page.locator('#create-cell select[name="service_domain"] option[value="onboarding"]').innerText(), "Onboarding");

      const apiCells = await page.evaluate(async () => (await fetch("/api/cells")).json());
      assert.equal(apiCells.find(c => c.id === "CELL-BRANCH-01").channel, "branch");
      assert.equal(apiCells.find(c => c.id === "CELL-BRANCH-01").domain, "general-banking");
      checks += 8;

      for (const id of ["dashboard", "cells", "routing", "simulation", "analytics", "events"]) {
        await page.locator('[data-view="' + id + '"]').click();
        assert.equal(await page.locator("#" + id).isVisible(), true);
        checks++;
      }

      await page.locator('[data-view="cells"]').click();
      const name = "SYN-E2E-" + viewport.width;
      await page.locator('#create-cell input[name="id"]').fill(name);
      await page.locator('#create-cell select[name="service_domain"]').selectOption("payments");
      await page.locator('#create-cell input[name="capacity"]').fill("2");
      await page.locator('#create-cell button').click();
      const row = page.locator("#cells-body tr").filter({ hasText: name });
      assert.equal(await row.locator("td").nth(1).innerText(), "Payments");
      assert.equal(await row.locator("td").nth(3).innerText(), "Borrador");
      page.once("dialog", dialog => dialog.accept());
      await row.getByRole("button", { name: "Activar", exact: true }).click();
      await page.waitForFunction(id => {
        const found = Array.from(document.querySelectorAll("#cells-body tr"))
          .find(element => element.cells[0]?.textContent === id);
        return found?.cells[3]?.textContent === "Activa";
      }, name);
      assert.equal(await row.locator("td").nth(3).innerText(), "Activa");
      checks += 3;

      await page.locator('[data-view="routing"]').click();
      await page.locator('#route select[name="service_domain"]').selectOption("payments");
      await page.locator('#route button').click();
      await page.locator("#route-output").getByText(/Solicitud SYN-/).waitFor();
      const metrics = await page.evaluate(async () => (await fetch("/api/metrics")).json());
      assert.ok(metrics.capacity_used >= 1);
      checks++;
      await page.getByRole("button", { name: "Completar y liberar capacidad" }).click();
      await page.getByText("Solicitud completada").waitFor();
      checks++;

      await page.locator('[data-view="simulation"]').click();
      await page.locator('#simulate select[name="service_domain"]').selectOption("onboarding");
      await page.locator('#simulate input[name="count"]').fill("2");
      await page.locator('#simulate button').click();
      await page.locator("#simulation-output").getByText(/simulation_id/).waitFor();
      assert.ok((await page.locator("#scenarios-body tr").count()) >= 1);
      assert.equal(await page.locator("#scenarios-body tr").first().locator("td").nth(1).innerText(), "Onboarding");
      assert.equal(await page.locator("#scenarios-body tr").first().locator("td").nth(2).innerText(), "Digital");
      checks += 3;

      await page.locator('[data-view="analytics"]').click();
      assert.ok((await page.locator("#requests-dist tr").count()) >= 1);
      assert.equal(await page.locator("#requests-dist tr").first().locator("td").nth(0).innerText(), "Onboarding");
      assert.equal(await page.locator("#requests-dist tr").first().locator("td").nth(1).innerText(), "Digital");
      checks += 3;

      await page.locator('[data-view="events"]').click();
      assert.ok((await page.locator("#events-body tr").count()) >= 1);
      checks++;

      // Verify accessible names for controls and label associations.
      assert.equal(await page.locator("button:not([aria-label])").evaluateAll(
        buttons => buttons.filter(button => !button.textContent.trim()).length), 0);
      assert.equal(await page.locator("input:not([id])").evaluateAll(
        inputs => inputs.filter(input => !input.closest("label")).length), 0);
      assert.equal(await page.locator("select").evaluateAll(
        selects => selects.filter(select => !select.closest("label")).length), 0);
      checks += 3;

      // Visible scroller content can extend beyond the viewport by design.
      // Validate real window scrolling and independent scroll inside the table.
      const geometry = await page.evaluate(() => {
        window.scrollTo(10000, 0);
        const windowHorizontalScroll = window.scrollX;
        window.scrollTo(0, 0);
        const tableScroller = document.querySelector("#events .table-wrap");
        const tableHasOverflow = tableScroller.scrollWidth > tableScroller.clientWidth;
        tableScroller.scrollLeft = 10000;
        const tableScrollWorks = tableScroller.scrollLeft > 0;
        tableScroller.scrollLeft = 0;
        const inspect = selector => {
          const element = document.querySelector(selector);
          return { width: Math.round(element.getBoundingClientRect().width),
            right: Math.round(element.getBoundingClientRect().right),
            clientWidth: element.clientWidth, scrollWidth: element.scrollWidth,
            overflowX: getComputedStyle(element).overflowX };
        };
        return { windowHorizontalScroll, tableHasOverflow, tableScrollWorks,
          html: inspect("html"), body: inspect("body"), main: inspect("main"),
          panel: inspect("#events"), scroller: inspect("#events .table-wrap"),
          table: inspect("#events table") };
      });
      console.log("RESPONSIVE_GEOMETRY", JSON.stringify({viewport, ...geometry}));
      assert.equal(geometry.windowHorizontalScroll, 0, "Page itself must not scroll horizontally");
      if (viewport.width <= 768) {
        assert.equal(geometry.tableHasOverflow, true, "Wide event table must have internal overflow on narrow viewports");
        assert.equal(geometry.tableScrollWorks, true, "Wide event table must be independently scrollable on narrow viewports");
      }
      assert.deepEqual(errors, [], "Browser JS errors or server failures");
      checks += 2;
      await page.close();
    }
    console.log("BROWSER_E2E_CHECKS=" + checks);
  } finally {
    await browser.close();
  }
})().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
