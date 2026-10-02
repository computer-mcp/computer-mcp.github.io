import { LinkChecker, LinkState } from "linkinator";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export function githubTarget(link) {
  const url = new URL(link);
  if (url.origin !== "https://github.com" || url.search || url.username || url.password)
    return null;
  const parts = url.pathname.replace(/\/$/, "").split("/").slice(1);
  if (parts[0] !== "computer-mcp" || !/^[\w.-]+$/.test(parts[1] ?? "")) return null;
  const repository = `${parts[0]}/${parts[1]}`;
  if (parts.length === 2) return { repository, kind: "repository" };
  if (parts.length === 3 && parts[2] === "releases") return { repository, kind: "releases" };
  if (parts.length === 4 && parts[2] === "releases" && parts[3] === "latest")
    return { repository, kind: "latest" };
  if (parts.length === 4 && parts[2] === "security" && parts[3] === "policy")
    return { repository, kind: "policy" };
  if (
    parts.length < 5 ||
    !["blob", "tree"].includes(parts[2]) ||
    !/^(main|master|[0-9a-f]{40})$/.test(parts[3])
  )
    return null;
  const path = parts.slice(4).map((part) => decodeURIComponent(part));
  if (path.some((part) => !part || part === "." || part === ".." || /[\\/]/.test(part)))
    return null;
  return {
    repository,
    kind: parts[2] === "blob" ? "file" : "directory",
    ref: parts[3],
    path: path.map(encodeURIComponent).join("/"),
  };
}

export async function githubJSON(endpoint) {
  const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
  const response = await fetch(`https://api.github.com/${endpoint}`, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "computer-mcp-website-link-check",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    redirect: "error",
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(`GitHub API returned HTTP ${response.status}`);
  return response.json();
}

export async function resolveFailures(links, request = githubJSON) {
  const requests = new Map();
  const get = (endpoint) => {
    if (!requests.has(endpoint))
      requests.set(
        endpoint,
        Promise.resolve().then(() => request(endpoint)),
      );
    return requests.get(endpoint);
  };
  const failures = [];
  const verified = [];
  for (const link of links.filter((item) => item.state === LinkState.BROKEN)) {
    try {
      const target = link.status >= 500 && link.status <= 599 ? githubTarget(link.url) : null;
      if (!target) {
        failures.push(link);
        continue;
      }
      const base = `repos/${target.repository}`;
      const repository = await get(base);
      if (
        repository.private !== false ||
        repository.full_name?.toLowerCase() !== target.repository.toLowerCase()
      )
        throw new Error("The target is not the expected public repository");
      if (target.kind !== "repository") {
        const endpoint = {
          releases: `${base}/releases`,
          latest: `${base}/releases/latest`,
          policy: `${base}/contents/SECURITY.md?ref=${encodeURIComponent(repository.default_branch)}`,
          file: `${base}/contents/${target.path}?ref=${target.ref}`,
          directory: `${base}/contents/${target.path}?ref=${target.ref}`,
        }[target.kind];
        const content = await get(endpoint);
        if (target.kind === "directory" || target.kind === "releases") {
          if (!Array.isArray(content)) throw new Error("The target is not the expected listing");
        } else if (target.kind === "latest") {
          if (
            content.draft !== false ||
            content.prerelease !== false ||
            !content.html_url?.startsWith(`https://github.com/${target.repository}/releases/tag/`)
          )
            throw new Error("The target has no public stable release");
        } else if (content.type !== "file") {
          throw new Error("The target is not a file");
        }
      }
      verified.push(link.url);
    } catch (error) {
      failures.push({ ...link, verificationError: error.message });
    }
  }
  return { failures, verified };
}

async function main() {
  const checker = new LinkChecker();
  checker.on("retry", ({ url, secondsUntilRetry }) =>
    console.log(`Retrying ${url} in ${secondsUntilRetry} seconds`),
  );
  const result = await checker.check({
    path: "dist",
    recurse: true,
    linksToSkip: ["^https://computer-mcp.github.io"],
    concurrency: 5,
    retryErrors: true,
    retryErrorsCount: 3,
    timeout: 30_000,
  });
  const { failures, verified } = await resolveFailures(result.links);
  for (const url of verified) console.log(`Verified through GitHub API: ${url}`);
  for (const link of failures)
    console.error(
      `[${link.status ?? "failed"}] ${link.url}: ${link.verificationError ?? "link failed"}`,
    );
  if (failures.length || (!result.passed && !verified.length)) {
    process.exitCode = 1;
    return;
  }
  console.log(`All ${result.links.length} links verified (${verified.length} through GitHub API).`);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url)
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
