import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";

test("presents the product contract and primary actions", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Computer MCP/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("用上你的本机工具");
  await expect(page.getByRole("tab")).toHaveCount(4);
  for (const [id, name] of [
    ["cli", "swift-format"],
    ["codex", "codex"],
  ]) {
    await page.locator(`#tab-${id}`).click();
    await expect(page.locator(`#panel-${id}`)).toBeVisible();
    await expect(page.locator(`#panel-${id} a`)).toHaveAttribute(
      "href",
      `https://github.com/computer-mcp/plugin-${name}`,
    );
  }
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("use your local tools");
  await expect(page.getByRole("link", { name: "Download for Mac" })).toHaveAttribute(
    "href",
    "https://github.com/computer-mcp/computer-mcp/releases/latest",
  );
});

test("switches capabilities with keyboard access and preserves the selected panel across languages", async ({
  page,
}) => {
  await page.goto("/");
  const cli = page.locator("#tab-cli");
  await cli.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#tab-codex")).toBeFocused();
  await expect(page.locator("#panel-codex")).toBeVisible();
  await expect(page.locator("#panel-cli")).toBeHidden();
  await page.keyboard.press("End");
  await expect(page.locator("#tab-skills")).toBeFocused();
  await expect(page.locator("#panel-skills")).toBeVisible();
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("#panel-skills")).toContainText("reusable instructions");
  await page.getByRole("button", { name: "切换为中文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.locator("#panel-skills")).toContainText("可复用的说明");
});

test("ships complete metadata and the GitHub Pages root contract", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /CLI/);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://computer-mcp.github.io/",
  );
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
    "content",
    "https://computer-mcp.github.io/og-image.png",
  );
  await expect((await request.get("/og-image.png")).status()).toBe(200);
  await expect((await request.get("/brand/mark.png")).status()).toBe(200);
  await expect((await request.get("/site.webmanifest")).status()).toBe(200);
  const releaseResponse = await request.get("/release.json");
  expect(releaseResponse.status()).toBe(200);
  expect(await releaseResponse.json()).toMatchObject({
    product: "Computer MCP",
    version: "1.2.1",
    source_commit: "d1f0e642aa822b6f43d8b417b4c20473a64bf0a2",
    release_tag: "v1.2.1",
    release_url: "https://github.com/computer-mcp/computer-mcp/releases/tag/v1.2.1",
  });
  expect(existsSync("public/CNAME"), "A custom-domain CNAME must not be present.").toBe(false);
});

test("separates host permissions from native Codex authority", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to English" }).click();
  const security = page.locator("#security");
  await expect(
    security.getByRole("heading", { name: "Three host permission modes" }),
  ).toBeVisible();
  await expect(security).toContainText("independent of profile names or connection channels");
  await expect(security).toContainText(
    "Local full access alone does not grant tools or enable Full Shell",
  );
  await expect(security).toContainText("The owner approves in the App or management CLI");
  await expect(security).toContainText("A model-supplied confirm field is not approval");
  const codex = page.locator(".codex-contract");
  await expect(codex).toContainText("App Server and Exec lifecycles through swift-codex");
  await expect(codex).toContainText(
    "Codex owns its configuration, provider, MCP, Skills, hooks and authentication",
  );
  await expect(codex).toContainText(
    "Omitted execution settings inherit Codex configuration, including native Full Access",
  );
  await expect(codex).toContainText(
    "Native approvals retain their decisions and scopes and cannot approve host tickets",
  );
});

test("states execution, integration and cancellation boundaries", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to English" }).click();
  await page.getByText("What are the execution boundaries?", { exact: true }).click();
  const limits = page.locator(".limitations");
  await expect(limits).toContainText("A working directory or worktree is not an OS sandbox");
  await expect(limits).toContainText(
    "Full Shell and native Codex Full Access carry the executing user's permissions",
  );
  await expect(limits).toContainText(
    "A cancellation request is not proof of completion or cleanup",
  );
  await expect(limits).toContainText("Unknown write results are not automatically replayed");
  await page.getByText("Can it operate desktop apps?", { exact: true }).click();
  await expect(page.getByText(/Availability depends on the operation/)).toBeVisible();
  await expect(
    page.locator('a[href="https://github.com/computer-mcp/plugin-computer-use"]'),
  ).toBeVisible();
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
  await expect(page.getByRole("link", { name: "跳转到正文" })).toBeFocused();
  await page.getByRole("button", { name: "Switch to English" }).click();

  const copy = page.getByRole("button", { name: /workspace.list/ });
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

  const copy = page.getByRole("button", { name: /workspace.list/ });
  await copy.click();

  await expect(copy).toHaveText("已选中文本");
  await expect(page.getByRole("status")).toHaveText("剪贴板不可用，已选中命令。");
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

  const menuButton = page.getByRole("button", { name: "菜单" });
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
