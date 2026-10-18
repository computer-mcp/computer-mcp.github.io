import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = "computer-mcp/computer-mcp";
const origin = `https://github.com/${repository}`;
const destination = new URL("../public/release.json", import.meta.url);

export function unpublishedRecord() {
  return {
    schema_version: 1,
    product: "Computer MCP",
    main_repository: origin,
    version: null,
    source_commit: null,
    release_tag: null,
    release_url: null,
  };
}

export function validateRecord(record) {
  if (
    !record ||
    record.schema_version !== 1 ||
    record.product !== "Computer MCP" ||
    record.main_repository !== origin
  ) {
    throw new Error("Release record identity is invalid");
  }
  if (
    [record.version, record.source_commit, record.release_tag, record.release_url].every(
      (value) => value === null,
    )
  )
    return record;
  if (
    !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(record.version) ||
    !/^[0-9a-f]{40}$/.test(record.source_commit) ||
    record.release_tag !== `v${record.version}` ||
    record.release_url !== `${origin}/releases/tag/${record.release_tag}`
  ) {
    throw new Error("Release record identity is invalid");
  }
  return record;
}

export function validateDelivery(record, release, commit, bytes) {
  validateRecord(record);
  if (record.version === null) throw new Error("A delivery must identify a published release");
  const assets = release.assets.filter((asset) => asset.name === "release.json");
  const digest = `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
  if (
    release.draft ||
    release.prerelease ||
    !release.published_at ||
    release.tag_name !== record.release_tag ||
    release.html_url !== record.release_url ||
    commit !== record.source_commit ||
    assets.length !== 1 ||
    assets[0].digest !== digest
  ) {
    throw new Error("Official published release, tag, or asset identity does not match");
  }
}

export function checkForward(previous, next) {
  validateRecord(previous);
  validateRecord(next);
  if (previous.version === null) return;
  if (next.version === null) throw new Error("A published release cannot disappear");
  const before = previous.version.split(".").map(Number);
  const after = next.version.split(".").map(Number);
  for (let index = 0; index < 3; index++) {
    if (after[index] < before[index]) throw new Error("Product version cannot go backwards");
    if (after[index] > before[index]) return;
  }
  if (JSON.stringify(previous) !== JSON.stringify(next)) {
    throw new Error("An existing release identity is immutable");
  }
}

function gh(...args) {
  return execFileSync("gh", args, { encoding: "utf8", timeout: 120_000 });
}

function publishedRecord(tag) {
  if (!/^v\d+\.\d+\.\d+$/.test(tag)) throw new Error("Pass a stable release tag");
  const release = JSON.parse(gh("api", `repos/${repository}/releases/tags/${tag}`));
  if (release.draft || release.prerelease)
    throw new Error("Release must already be public and stable");
  const temporary = mkdtempSync(join(tmpdir(), "computer-mcp-site-release-"));
  try {
    gh(
      "release",
      "download",
      tag,
      "--repo",
      repository,
      "--pattern",
      "release.json",
      "--dir",
      temporary,
    );
    const bytes = readFileSync(join(temporary, "release.json"));
    const record = JSON.parse(bytes);
    const commit = gh("api", `repos/${repository}/commits/${tag}`, "--jq", ".sha").trim();
    validateDelivery(record, release, commit, bytes);
    return record;
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

export function latestRecord(api = gh, readPublished = publishedRecord) {
  const pages = JSON.parse(
    api("api", `repos/${repository}/releases?per_page=100`, "--paginate", "--slurp"),
  );
  if (!Array.isArray(pages) || pages.length === 0 || pages.some((page) => !Array.isArray(page))) {
    throw new Error("Invalid published release listing");
  }
  const releases = pages.flat();
  if (
    releases.some(
      (release) =>
        !release || typeof release.draft !== "boolean" || typeof release.prerelease !== "boolean",
    )
  ) {
    throw new Error("Invalid published release listing");
  }
  if (!releases.some((release) => !release.draft && !release.prerelease))
    return unpublishedRecord();
  const latest = JSON.parse(api("api", `repos/${repository}/releases/latest`));
  return readPublished(latest.tag_name);
}

export function main(
  args,
  { path = destination, latest = latestRecord, published = publishedRecord } = {},
) {
  const previous = validateRecord(JSON.parse(readFileSync(path)));
  if (args.length === 1 && args[0] === "check") {
    console.log(`Release record valid: ${previous.release_tag ?? "no published stable release"}`);
    return;
  }
  if (args.length !== 2 || !["update", "verify-public"].includes(args[0])) {
    throw new Error(
      "Usage: release.mjs check | update latest|vX.Y.Z | verify-public latest|vX.Y.Z",
    );
  }
  const record = args[1] === "latest" ? latest() : published(args[1]);
  checkForward(previous, record);
  if (args[0] === "update") {
    writeFileSync(path, `${JSON.stringify(record, null, 2)}\n`);
  } else if (JSON.stringify(previous) !== JSON.stringify(record)) {
    throw new Error("Website record differs from the official delivered record");
  }
  console.log(`Official delivery verified: ${record.release_tag ?? "no published stable release"}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2));
}
