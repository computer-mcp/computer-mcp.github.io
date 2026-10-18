import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  checkForward,
  latestRecord,
  main,
  unpublishedRecord,
  validateDelivery,
  validateRecord,
} from "./release.mjs";
import { renderReleaseLinks } from "./release-html.mjs";

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

test("unpublished records carry no release identity and accept the first delivery", () => {
  const empty = unpublishedRecord();
  assert.equal(validateRecord(empty), empty);
  checkForward(empty, empty);
  checkForward(empty, record);
  for (const key of ["version", "source_commit", "release_tag", "release_url"]) {
    assert.throws(() => validateRecord({ ...empty, [key]: record[key] }));
    assert.throws(() => validateRecord({ ...empty, [key]: undefined }));
  }
  assert.throws(() => checkForward(record, empty));
  assert.throws(() => validateDelivery(empty, delivery, record.source_commit, bytes));
});

test("a successful complete listing distinguishes no stable release from API failures", () => {
  for (const pages of [
    [[]],
    [[{ draft: true, prerelease: false }]],
    [[{ draft: false, prerelease: true }]],
  ]) {
    const calls = [];
    const result = latestRecord(
      (...args) => {
        calls.push(args);
        return JSON.stringify(pages);
      },
      () => assert.fail("No release asset should be requested"),
    );
    assert.deepEqual(result, unpublishedRecord());
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].slice(-2), ["--paginate", "--slurp"]);
  }
  for (const pages of [null, [], {}, [[{}]], [[null]]]) {
    assert.throws(() => latestRecord(() => JSON.stringify(pages)));
  }
  assert.throws(
    () =>
      latestRecord(() => {
        throw new Error("HTTP 403");
      }),
    /HTTP 403/,
  );
  assert.equal(
    latestRecord(
      (...args) =>
        JSON.stringify(
          args[1].endsWith("/latest")
            ? { tag_name: record.release_tag }
            : [[], [{ draft: false, prerelease: false }]],
        ),
      (tag) => {
        assert.equal(tag, record.release_tag);
        return record;
      },
    ),
    record,
  );
});

test("the importer checks, updates and verifies the no-release state without changing failed imports", () => {
  const directory = mkdtempSync(join(tmpdir(), "website-release-test-"));
  const path = join(directory, "release.json");
  const empty = unpublishedRecord();
  const options = { path, latest: () => empty };
  try {
    writeFileSync(path, JSON.stringify(empty));
    main(["check"], options);
    main(["update", "latest"], options);
    main(["verify-public", "latest"], options);
    assert.deepEqual(JSON.parse(readFileSync(path)), empty);
    const before = readFileSync(path);
    assert.throws(() =>
      main(["update", "latest"], {
        path,
        latest: () => {
          throw new Error("HTTP 500");
        },
      }),
    );
    assert.deepEqual(readFileSync(path), before);
    assert.throws(() => main(["verify-public", "latest"], { path, latest: () => record }));
    main(["update", "latest"], { path, latest: () => record });
    assert.deepEqual(JSON.parse(readFileSync(path)), record);
    assert.throws(() => main(["update", "latest"], options));
    assert.deepEqual(JSON.parse(readFileSync(path)), record);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("both static pages render downloads only for a delivered release", () => {
  for (const path of ["index.html", "guide/index.html"]) {
    const html = readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
    const count = [...html.matchAll(/data-release-link/g)].length;
    assert.ok(count > 0);
    const empty = renderReleaseLinks(html, unpublishedRecord());
    assert.equal(
      [...empty.matchAll(/<span data-en="No releases yet">尚无发布版本<\/span>/g)].length,
      count,
    );
    assert.doesNotMatch(empty, /data-release-link|\/releases\/latest|\/releases\/tag\//);
    const available = renderReleaseLinks(html, record);
    assert.equal(available.split(`href="${record.release_url}"`).length - 1, count);
    assert.match(available, /data-en="Download/);
    assert.doesNotMatch(available, /No releases yet/);
  }
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
