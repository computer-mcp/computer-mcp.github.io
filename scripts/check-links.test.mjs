import assert from "node:assert/strict";
import test from "node:test";
import { githubJSON, githubTarget, resolveFailures } from "./check-links.mjs";

const repository = {
  private: false,
  full_name: "computer-mcp/computer-mcp",
  default_branch: "master",
};
const fileURL =
  "https://github.com/computer-mcp/computer-mcp/blob/master/Documentation/Reference/QuickStart.md";
const broken = (url, status = 503) => ({ url, status, state: "BROKEN" });

test("a GitHub service error requires a public repository and the exact file", async () => {
  const endpoints = [];
  const result = await resolveFailures([broken(fileURL)], async (endpoint) => {
    endpoints.push(endpoint);
    return endpoint === "repos/computer-mcp/computer-mcp" ? repository : { type: "file" };
  });
  assert.deepEqual(endpoints, [
    "repos/computer-mcp/computer-mcp",
    "repos/computer-mcp/computer-mcp/contents/Documentation/Reference/QuickStart.md?ref=master",
  ]);
  assert.deepEqual(result, { failures: [], verified: [fileURL] });
});

test("a missing file or failed API leaves the link failed", async () => {
  const result = await resolveFailures([broken(fileURL)], async (endpoint) => {
    if (endpoint === "repos/computer-mcp/computer-mcp") return repository;
    throw new Error("HTTP 404");
  });
  assert.equal(result.failures.length, 1);
  assert.deepEqual(result.verified, []);
});

test("file and directory routes retain their target type", async () => {
  const directoryURL = "https://github.com/computer-mcp/computer-mcp/tree/master/Documentation";
  const result = await resolveFailures(
    [broken(fileURL), broken(directoryURL)],
    async (endpoint) => {
      return endpoint === "repos/computer-mcp/computer-mcp" ? repository : [];
    },
  );
  assert.equal(result.failures[0].url, fileURL);
  assert.deepEqual(result.verified, [directoryURL]);
});

test("private or different repositories cannot satisfy public links", async () => {
  for (const value of [
    { ...repository, private: true },
    { ...repository, full_name: "computer-mcp/another-repository" },
  ]) {
    let calls = 0;
    const result = await resolveFailures([broken(fileURL)], async () => {
      calls += 1;
      return value;
    });
    assert.equal(calls, 1);
    assert.equal(result.failures.length, 1);
  }
});

test("client errors, other hosts and unsupported GitHub routes use their HTTP result", async () => {
  const links = [
    broken(fileURL, 404),
    broken(fileURL, 403),
    broken(fileURL, 0),
    broken("https://example.com/document"),
    broken("https://github.com/another-owner/repository/blob/master/document.md"),
    broken("https://github.com/computer-mcp/computer-mcp/issues/1"),
  ];
  const result = await resolveFailures(links, () => assert.fail("Unexpected GitHub API request"));
  assert.deepEqual(result.failures, links);
  assert.deepEqual(result.verified, []);
});

test("encoded path separators and ambiguous branch routes retain HTTP validation", () => {
  assert.equal(
    githubTarget("https://github.com/computer-mcp/computer-mcp/blob/master/a%2Fb.md"),
    null,
  );
  assert.equal(
    githubTarget("https://github.com/computer-mcp/computer-mcp/blob/feature/branch/a.md"),
    null,
  );
  assert.equal(
    githubTarget("https://github.com/computer-mcp/computer-mcp/blob/master/a.md?raw=true"),
    null,
  );
});

test("repository metadata is reused and latest releases must be public and stable", async () => {
  const latest = "https://github.com/computer-mcp/computer-mcp/releases/latest";
  let metadataCalls = 0;
  const result = await resolveFailures([broken(latest), broken(fileURL)], async (endpoint) => {
    if (endpoint === "repos/computer-mcp/computer-mcp") {
      metadataCalls += 1;
      return repository;
    }
    if (endpoint.endsWith("/latest")) return { draft: true, prerelease: false };
    return { type: "file" };
  });
  assert.equal(metadataCalls, 1);
  assert.equal(result.failures[0].url, latest);
  assert.deepEqual(result.verified, [fileURL]);
});

test("public repository, release and policy routes require their corresponding API target", async () => {
  const urls = [
    "https://github.com/computer-mcp/computer-mcp",
    "https://github.com/computer-mcp/computer-mcp/releases",
    "https://github.com/computer-mcp/computer-mcp/releases/latest",
    "https://github.com/computer-mcp/computer-mcp/security/policy",
  ];
  const responses = new Map([
    ["repos/computer-mcp/computer-mcp", repository],
    ["repos/computer-mcp/computer-mcp/releases", []],
    [
      "repos/computer-mcp/computer-mcp/releases/latest",
      {
        draft: false,
        prerelease: false,
        html_url: "https://github.com/computer-mcp/computer-mcp/releases/tag/example-tag",
      },
    ],
    ["repos/computer-mcp/computer-mcp/contents/SECURITY.md?ref=master", { type: "file" }],
  ]);
  const result = await resolveFailures(
    urls.map((url) => broken(url)),
    async (endpoint) => {
      assert.ok(responses.has(endpoint));
      return responses.get(endpoint);
    },
  );
  assert.deepEqual(result, { failures: [], verified: urls });
});

test("API credentials are confined to the fixed GitHub API origin", async () => {
  const originalToken = process.env.GH_TOKEN;
  const originalFetch = globalThis.fetch;
  process.env.GH_TOKEN = "test-credential";
  globalThis.fetch = async (url, options) => {
    assert.equal(new URL(url).origin, "https://api.github.com");
    assert.equal(options.method, "GET");
    assert.equal(options.headers.Authorization, "Bearer test-credential");
    assert.equal(options.redirect, "error");
    return { ok: true, json: async () => repository };
  };
  try {
    assert.deepEqual(await githubJSON("repos/computer-mcp/computer-mcp"), repository);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalToken === undefined) delete process.env.GH_TOKEN;
    else process.env.GH_TOKEN = originalToken;
  }
});
