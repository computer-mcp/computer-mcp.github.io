# Official plugin catalog

The publisher generates `public/plugins/index.json`, which belongs at `/plugins/index.json` in a
complete Pages artifact. This JSON describes published plugin releases for discovery and version
selection. It grants no execution permission and is not an artifact signature. The host installer
must still revalidate the selected GitHub Release, repository identity and asset membership, then
verify the downloaded bytes and package using its existing installation rules.

The generator, policy, serialized publication workflow and offline tests are available in this
repository. Public catalog delivery requires a complete verified initial snapshot committed to
`main`. Until that prerequisite is satisfied, publication fails before upload and retains the
deployed site. Plugin notification delivery and the live endpoint require separate acceptance.

The host's
[plugin package reference](https://github.com/computer-mcp/computer-mcp/blob/master/Documentation/Reference/PluginPackages.md)
owns manifest, compatibility and installation semantics. This generator validates a metadata
projection and the exact manifest bytes; it does not replace the host's complete package validator.

## Generate and check

Python 3.11 or newer is required; the publisher uses only the standard library. Run:

```sh
npm run catalog:update -- --use-gh-auth
npm run catalog:check
npm run catalog:check-policy
npm run catalog:test
```

The optional authentication flag reads the existing GitHub CLI token into memory. Environment
`GH_TOKEN` or `GITHUB_TOKEN` takes precedence. No token is written to the catalog, passed to package
code or forwarded to an asset redirect. Public unauthenticated API requests work within GitHub's
rate limits. An inaccessible release or exhausted request budget fails the entire generation.

`--output <path>` and `--policy <path>` support isolated candidates. `check` performs no network
requests. The generated file has deterministic UTF-8 JSON bytes, two-space indentation, sorted
object keys and a trailing newline. It is excluded from Prettier because the publisher owns this
serialization. `--require-existing` refuses to initialize a missing catalog before making source
requests; automation always uses this option.

## Schema 1

| Field            | Meaning                                                                                  |
| ---------------- | ---------------------------------------------------------------------------------------- |
| `schema_version` | Integer `1`; other schemas require explicit client support.                              |
| `publisher`      | Official organization login and numeric identity.                                        |
| `generation`     | Positive integer incremented only when catalog content changes.                          |
| `revision`       | SHA-256 of the canonical object containing `schema_version`, `publisher` and `releases`. |
| `generated_at`   | UTC time of the content generation, in `YYYY-MM-DDTHH:MM:SSZ` format.                    |
| `releases`       | Complete records sorted by numeric repository ID and release ID.                         |

Each release record contains:

- Numeric `repository_id` and `release_id`, canonical `repository`, exact `tag`, `commit`,
  `manifest_blob_sha` and `manifest_sha256`.
- Manifest `plugin_id`, `name`, semantic `version`, nullable `summary` and `contributions` with
  `mcp`, `cli` and `skills` identifier arrays.
- `compatibility` with `platforms`, `architectures`, nullable `minimum_host` and nullable
  `maximum_host`. Schema 1 represents the host's existing macOS package format, so `platforms` is
  `['macos']`. This value is not inferred from package contents. Architectures come from the
  released manifest; an empty array imposes no architecture restriction. The minimum is inclusive
  and the maximum exclusive, following the host's semantic version precedence.
- `dependencies`, containing manifest dependency IDs, command names, application locators, human
  setup instructions and nullable documentation URLs. These are prerequisites the user supplies, not
  instructions to install software automatically.
- Boolean `prerelease`, UTC `published_at`, boolean `withdrawn` and nullable `withdrawal_reason`. A
  withdrawn version stays visible as a historical identity and cannot be selected for installation.
- `assets`, sorted by numeric asset ID. Each archive carries `id`, `name`, `size` in bytes, `sha256`
  and its exact official browser download `url`.

IDs are positive integers at most 9,007,199,254,740,991. Plugin IDs cannot move between numeric
repository identities. A repository cannot advertise duplicate versions or tags, and archive IDs are
unique throughout the snapshot. Build metadata is part of version identity but does not alter
compatibility precedence. Clients should use the release channel flag for prerelease selection.

An unchanged reconciliation preserves the entire prior snapshot, including generation and time.
Clients therefore measure cache freshness from a successful fetch or conditional response;
`generated_at` alone does not indicate an outage.

## Provenance and withdrawals

`scripts/plugin-catalog-policy.json` admits official repositories by both name and numeric ID.
Adding a repository requires a reviewed publisher policy change and no host release. The generator
checks that each source is a public, active, non-fork repository of the configured organization. It
enumerates published releases, resolves each exact tag to a commit and reads the root
`computer-mcp-plugin.toml` at that commit. It checks the Git blob identity, tag/version agreement,
manifest projection, release-owned assets, uploaded state, size and SHA-256.

Every advertised archive is downloaded within bounded budgets. The generator reads the root manifest
directly from ZIP or tar, compares its bytes with the tagged manifest, and never extracts or
executes package code. It checks release, tag and asset identities again after downloading.
Non-archive receipt files are not advertised as installable archives. A published release with no
complete verified archive fails generation; a draft is not advertised.

Existing package identities are immutable. Changing their tag commit, declaration, asset ID, name,
digest or size fails generation. Promoting a prerelease to the stable channel preserves the same
package identity. Missing releases, missing assets and network failures do not imply withdrawal.

To withdraw a version, add a record to the policy's `withdrawals` array:

```json
{
  "repository_id": 123,
  "release_id": 456,
  "reason": "A concise explanation for people selecting this version."
}
```

The record must identify a previously verified or currently verifiable release. The publisher
retains its verified metadata and marks it withdrawn, including when the upstream release has
disappeared. A deleted repository can be removed from the repository allowlist only when all its
previously advertised releases have explicit withdrawals. Removing a withdrawal does not silently
restore a version; deliver a new release instead.

## Publication and failure behavior

Writers for one destination serialize across processes. Each writer reads the previous snapshot
after obtaining the lock, rebuilds the complete catalog, validates every record and only then
replaces the file atomically. No independent plugin job writes shared catalog records. Duplicate
events are idempotent; a complete reconciliation discovers releases even when their notification was
missed. A detected external edit aborts publication. File and directory synchronization make the
replacement durable; failures before replacement leave the previous bytes intact.

The committed canonical `public/plugins/index.json` on `main` is the durable generation authority.
Initialize it by generating and reviewing a complete verified snapshot, then committing it with the
publisher policy. Automation never uses a missing file as permission to reset generation, and never
restores authority from a CDN response, an Actions cache or an expiring artifact.

The official repository's `pages.yml` workflow reconciles hourly at minute 37, on `main` pushes and
through `workflow_dispatch`. One `pages` concurrency group covers generation through deployment;
active runs are not cancelled. Each run checks out current `main` after entering the group and
verifies its seed before requesting release metadata. It always scans every admitted repository, so
missed notifications and replaced pending runs are repaired by the next successful reconciliation.

After generation, the workflow validates and tests the complete site. The publication helper checks
the catalog successor, exact built index bytes and unchanged source, then commits only the new index
as a child of the checked-out commit. It uses a normal fast-forward push, never a force push. A
concurrent source update rejects publication; the next run starts from current `main`. Identical
catalog content creates no commit. Unrelated local or staged changes are rejected and preserved.

Only then does Pages upload and deploy the complete artifact. Generation, validation or commit
failure prevents upload and preserves the deployed artifact. If deployment fails after the verified
index commit, the next run uses that committed generation and can deploy it without incrementing
generation. A local generated file alone does not deploy anything. Publisher tests also run in
read-only website CI, without contacting release sources.

The central build job uses its short-lived GitHub job token with `contents: write` to persist the
index; the deployment job has Pages and identity-token permissions. Plugin notification senders
should invoke `pages.yml` on `main` using `workflow_dispatch`, with Actions write access scoped to
this receiving repository. They do not need website Contents write access. Notification payloads
provide no metadata or policy overrides. Existing GitHub authentication is an operator input; this
repository does not create credentials. If notifications are unavailable, scheduled and manual
reconciliation still use the same complete verification path.

The index is bounded to 4 MiB and 1,024 releases. A manifest is at most 1 MiB; each archive is at
most 512 MiB, with at most 20,000 entries and the host package format's expansion/path bounds. A
publisher run has a 10-minute deadline, at most 1,024 API requests and at most 1 GiB of archive
downloads. HTTP responses are bounded while streaming. Transient server/rate errors receive at most
three attempts; a server delay longer than 30 seconds fails the run rather than ignoring it. These
are generation failure bounds, not permission to truncate the catalog or omit old releases.

Tests cover provenance rejection, immutable identities, explicit withdrawal, failed writes,
concurrent publishers, duplicate events, invalid/oversized/truncated input, bounded retries,
manifest/archive agreement, safe manifest reads, credential-free redirects, committed generation
continuity, concurrent source pushes and deployment retry. Network discovery in the host remains a
separate consumer; installation must retain its exact GitHub revalidation.
