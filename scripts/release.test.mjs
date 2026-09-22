import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { checkForward, validateDelivery, validateRecord } from "./release.mjs";

const record = {
  schema_version: 1,
  product: "Computer MCP",
  version: "2.3.4",
  main_repository: "https://github.com/computer-mcp/computer-mcp",
  source_commit: "a".repeat(40),
  release_tag: "v2.3.4",
  release_url: "https://github.com/computer-mcp/computer-mcp/releases/tag/v2.3.4",
};
const bytes = Buffer.from(JSON.stringify(record));
const delivery = {
  draft: false,
  prerelease: false,
  published_at: "2026-01-01T00:00:00Z",
  tag_name: record.release_tag,
  html_url: record.release_url,
  assets: [
    { name: "release.json", digest: `sha256:${createHash("sha256").update(bytes).digest("hex")}` },
  ],
};

test("accepts one coherent official delivered identity", () => {
  validateDelivery(record, delivery, record.source_commit, bytes);
  checkForward(record, { ...record });
});

test("rejects stale duplicated fields, draft releases, changed bytes and wrong commits", () => {
  assert.throws(() => validateRecord({ ...record, version: "2.3.5" }));
  assert.throws(() =>
    validateDelivery(record, { ...delivery, draft: true }, record.source_commit, bytes),
  );
  assert.throws(() => validateDelivery(record, delivery, "b".repeat(40), bytes));
  assert.throws(() =>
    validateDelivery(record, delivery, record.source_commit, Buffer.from("changed")),
  );
  assert.throws(() => checkForward(record, { ...record, source_commit: "b".repeat(40) }));
  assert.throws(() =>
    checkForward(record, {
      ...record,
      version: "2.3.3",
      release_tag: "v2.3.3",
      release_url: record.release_url.replace("2.3.4", "2.3.3"),
    }),
  );
});
