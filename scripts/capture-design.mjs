import { chromium } from "@playwright/test";
import { fileURLToPath } from "node:url";

const browser = await chromium.launch();
try {
  for (const [name, width, height] of [
    ["desktop", 1488, 1058],
    ["mobile", 393, 851],
  ]) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    await page.goto(process.argv[2] || "http://127.0.0.1:4173", { waitUntil: "networkidle" });
    await page.locator("#panel-cli").waitFor({ state: "visible" });
    if (name === "mobile") await page.locator("[data-menu-toggle]").focus();
    await page.screenshot({
      path: fileURLToPath(new URL(`../Design/References/${name}.png`, import.meta.url)),
    });
    await page.close();
  }
} finally {
  await browser.close();
}
