import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { validateRecord } from "../scripts/release.mjs";

const release = "https://github.com/computer-mcp/computer-mcp/releases/latest";

test("presents the product and its primary actions in both languages", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Computer MCP/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("聊天在哪，你的电脑就在哪。");
  await expect(page.locator(".hero").getByRole("link", { name: "下载 Mac 版" })).toHaveAttribute(
    "href",
    release,
  );
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Wherever you chat, your computer is there.",
  );
  await expect(page).toHaveTitle("Computer MCP — Wherever you chat, your computer is there.");
  const hero = page.locator(".hero");
  await expect(hero.getByRole("link", { name: "Download for Mac" })).toHaveAttribute(
    "href",
    release,
  );
  await expect(hero.getByRole("link", { name: "Setup guide" })).toHaveAttribute("href", "/guide/");
});

test("shows six capability examples with their plugins", async ({ page }) => {
  await page.goto("/");
  const capabilities = page.locator("#capabilities .capability");
  await expect(capabilities).toHaveCount(6);
  for (const name of ["swift-format", "computer-use", "codex", "claude", "cursor"]) {
    await expect(
      page.locator(`#capabilities a[href="https://github.com/computer-mcp/plugin-${name}"]`),
    ).toBeVisible();
  }
  await expect(page.locator("#capabilities")).toContainText("Codex 高级编排仍是实验能力");
});

test("keeps the chosen language across pages", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to English" }).click();
  await page.goto("/guide/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "From install to your first tool call.",
  );
  await expect(page.getByRole("link", { name: "Full ChatGPT steps" })).toHaveAttribute(
    "href",
    /ChatGPTWebRunbook\.md$/,
  );
  await page.getByRole("button", { name: "切换为中文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByRole("link", { name: "ChatGPT 完整步骤" })).toHaveAttribute(
    "href",
    /zh-CN\/ChatGPT\.md$/,
  );
  await page.goto("/?lang=en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Wherever you chat, your computer is there.",
  );
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
    "https://computer-mcp.github.io/brand/social-en.png",
  );
  for (const path of [
    "/brand/social-en.png",
    "/brand/icon.svg",
    "/brand/favicon.svg",
    "/brand/favicon-32.png",
    "/brand/apple-touch-icon.png",
    "/site.webmanifest",
    "/guide/",
  ]) {
    expect((await request.get(path)).status(), path).toBe(200);
  }
  const releaseResponse = await request.get("/release.json");
  expect(releaseResponse.status()).toBe(200);
  const record = validateRecord(await releaseResponse.json());
  expect(record).toEqual(JSON.parse(readFileSync("public/release.json")));
  expect(existsSync("public/CNAME"), "A custom-domain CNAME must not be present.").toBe(false);
});

test("separates host permissions from native Codex authority", async ({ page }) => {
  await page.goto("/");
  const permissions = page.locator("#permissions");
  await expect(permissions.getByRole("heading", { name: "观察" })).toBeVisible();
  await expect(permissions).toContainText("授权默认仅本次会话");
  await expect(permissions).toContainText("工作区不是沙箱");
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(permissions.getByRole("heading", { name: "Observe" })).toBeVisible();
  await expect(permissions).toContainText("Observe permits inspection without system changes");
  await expect(permissions).toContainText("never permits arbitrary execution");
  await expect(permissions).toContainText("Approval defaults to This Session");
  await expect(permissions).toContainText("Always Allow this Client is a separate choice");
  await expect(permissions).toContainText("Changes apply to new requests immediately");
  await expect(permissions).toContainText("a workspace is not a sandbox");
  await expect(permissions).toContainText(
    "macOS privacy permissions require their own authorization",
  );
  await page.getByText("Does it change my Codex settings?", { exact: true }).click();
  const codex = page.locator(".codex-contract");
  await expect(codex).toContainText("App Server and Exec lifecycles through swift-codex");
  await expect(codex).toContainText(
    "Codex owns its configuration, provider, MCP, Skills, hooks and authentication",
  );
  await expect(codex).toContainText(
    "Omitted execution settings inherit Codex configuration, including native Full Access",
  );
  await expect(codex).toContainText("cannot approve host tickets");
});

test("states execution, integration and cancellation boundaries", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to English" }).click();
  await page.getByText("What are the execution boundaries?", { exact: true }).click();
  const limits = page.locator(".limitations");
  await expect(limits).toContainText("A working directory or worktree is not an OS sandbox");
  await expect(limits).toContainText(
    "Host Full Access and native Codex Full Access carry the executing user's permissions",
  );
  await expect(limits).toContainText(
    "A cancellation request is not proof of completion or cleanup",
  );
  await expect(limits).toContainText("Unknown write results are not automatically replayed");
  await page.getByText("Can it operate desktop apps?", { exact: true }).click();
  await expect(page.getByText(/Availability depends on the operation, macOS/)).toBeVisible();
});

test("dates and sources the product comparison", async ({ page }) => {
  await page.goto("/");
  const comparison = page.locator("#comparison");
  await expect(comparison.locator("tbody tr")).toHaveCount(6);
  await expect(comparison.locator('time[datetime="2026-10-01"]')).toBeVisible();
  for (const href of [
    "https://learn.chatgpt.com/docs/dots/computers-and-apps",
    "https://openai.com/index/introducing-dots/",
    "https://learn.chatgpt.com/docs/remote",
    "https://learn.chatgpt.com/docs/remote-connections",
  ]) {
    await expect(comparison.locator(`a[href="${href}"]`)).toHaveCount(1);
  }
  await expect(comparison).toContainText("不代表免费或不限量");
});

for (const path of ["/", "/guide/"]) {
  test(`keeps every local navigation target on ${path} resolvable`, async ({ page }) => {
    await page.goto(path);
    const anchors = await page
      .locator('a[href^="#"]')
      .evaluateAll((links) => links.map((link) => link.getAttribute("href")));
    for (const href of anchors) {
      expect(await page.locator(href).count(), `Missing anchor target ${href}`).toBe(1);
    }
    for (const href of await page
      .locator('a[href^="/"]')
      .evaluateAll((links) => links.map((link) => link.getAttribute("href")))) {
      const [target, anchor] = href.split("#");
      const response = await page.request.get(target);
      expect(response.status(), href).toBe(200);
      if (anchor) expect(await response.text(), href).toContain(`id="${anchor}"`);
    }
  });

  for (const colorScheme of ["light", "dark"]) {
    test(`has no automated accessibility violations on ${path} in ${colorScheme} mode`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      await page.goto(path);
      const results = await new AxeBuilder({ page }).analyze();
      const violations = results.violations.flatMap((violation) =>
        violation.nodes.map(
          (node) =>
            `${violation.id}: ${node.target.join(" ")} — ${node.failureSummary?.replaceAll("\n", " ")}`,
        ),
      );
      expect(violations).toEqual([]);
    });
  }
}

test("supports keyboard navigation and command copy", async ({ context, page, browserName }) => {
  test.skip(browserName !== "chromium", "Clipboard behavior is validated in Chromium.");
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://127.0.0.1:4173",
  });
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到正文" })).toBeFocused();
  await page.getByRole("button", { name: "Switch to English" }).click();

  const copy = page.getByRole("button", { name: /workspace.list/ });
  await copy.scrollIntoViewIfNeeded();
  await copy.click();
  await expect(copy).toHaveText("Copied");
  await expect(page.getByRole("status")).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("workspace.list");
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
  for (const path of ["/", "/guide/"]) {
    await page.goto(path);
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
    expect(widths.document, path).toBeLessThanOrEqual(widths.viewport);
  }
});
