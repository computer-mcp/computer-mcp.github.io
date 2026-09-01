import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";

test("presents the product contract and primary actions", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/Computer MCP/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Your agents can act locally.",
  );
  await expect(page.getByText("A control plane, not a tool pile.")).toBeVisible();
  await expect(page.getByText("Computer MCP is not Codex Remote.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download latest release" })).toHaveAttribute(
    "href",
    "https://github.com/computer-mcp/computer-mcp/releases/latest",
  );
});

test("ships complete metadata and the GitHub Pages root contract", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /policy/i);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://computer-mcp.github.io/",
  );
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
    "content",
    "https://computer-mcp.github.io/og-image.png",
  );
  await expect((await request.get("/og-image.png")).status()).toBe(200);
  await expect((await request.get("/favicon.svg")).status()).toBe(200);
  await expect((await request.get("/site.webmanifest")).status()).toBe(200);
  expect(existsSync("public/CNAME"), "A custom-domain CNAME must not be present.").toBe(false);
});

test("keeps every local navigation target resolvable", async ({ page }) => {
  await page.goto("/");

  const anchors = await page
    .locator('a[href^="#"]')
    .evaluateAll((links) => links.map((link) => link.getAttribute("href")));

  for (const href of anchors) {
    expect(href).toBeTruthy();
    expect(await page.locator(href).count(), `Missing anchor target ${href}`).toBe(1);
  }
});

test("has no automated accessibility violations", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page }).analyze();
  const violations = results.violations.flatMap((violation) =>
    violation.nodes.map(
      (node) =>
        `${violation.id}: ${node.target.join(" ")} — ${node.failureSummary?.replaceAll("\n", " ")}`,
    ),
  );

  expect(violations).toEqual([]);
});

test("supports keyboard navigation and command copy", async ({ context, page, browserName }) => {
  test.skip(browserName !== "chromium", "Clipboard behavior is validated in Chromium.");
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://127.0.0.1:4173",
  });
  await page.goto("/");

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();

  const copy = page.getByRole("button", { name: "Copy workspace.list" });
  await copy.scrollIntoViewIfNeeded();
  await copy.click();
  await expect(copy).toHaveText("Copied");
  await expect(page.getByRole("status")).toHaveText("Copied");
});

test("selects the command when clipboard access is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new DOMException("Clipboard access denied", "NotAllowedError");
        },
      },
    });
  });
  await page.goto("/");

  const copy = page.getByRole("button", { name: "Copy workspace.list" });
  await copy.click();

  await expect(copy).toHaveText("Text selected");
  await expect(page.getByRole("status")).toHaveText("Clipboard unavailable. Command selected.");
  await expect(copy).toBeFocused();
  await expect
    .poll(() => page.evaluate(() => window.getSelection()?.toString()))
    .toBe("workspace.list");
});

test("mobile menu opens, closes with Escape, and does not overflow", async ({ page }, testInfo) => {
  test.skip(
    !testInfo.project.name.startsWith("mobile"),
    "Mobile behavior uses the mobile project.",
  );
  await page.goto("/");

  const menuButton = page.getByRole("button", { name: "Toggle navigation" });
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  await menuButton.click();
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  await expect(menuButton).toBeFocused();

  const widths = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
});
