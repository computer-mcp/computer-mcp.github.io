# Official plugin catalog

The publisher generates `public/plugins/index.json`, which belongs at `/plugins/index.json` in a
complete Pages artifact. This JSON describes current published plugin releases for discovery and
selection. Each repository contributes its highest stable semantic version and, when newer, its
highest prerelease. API order and publication time do not choose the version. The catalog is a
current release set for paired host/plugin delivery, with no historical compatibility fallback. It
grants no execution permission and is not an artifact signature. The host installer must still
revalidate the selected GitHub Release, repository identity and asset membership, then verify the
downloaded bytes and package using its existing installation rules.

Publication requires a complete verified snapshot committed to `master`; without one, publication
fails before upload and the deployed site is retained.

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

## Schema 2

| Field            | Meaning                                                                                  |
| ---------------- | ---------------------------------------------------------------------------------------- |
| `schema_version` | Integer `2`; schema 1 remains readable with inherited macOS archive targets.             |
| `publisher`      | Official organization login and numeric identity.                                        |
| `generation`     | Positive integer incremented only when catalog content changes.                          |
| `revision`       | SHA-256 of the canonical object containing `schema_version`, `publisher` and `releases`. |
| `generated_at`   | UTC time of the content generation, in `YYYY-MM-DDTHH:MM:SSZ` format.                    |
| `releases`       | Current release records sorted by numeric repository ID and release ID.                  |

Each release record contains:

- Numeric `repository_id` and `release_id`, canonical `repository`, exact `tag`, `commit`,
  `manifest_blob_sha` and `manifest_sha256`.
- Manifest `plugin_id`, `name`, semantic `version`, nullable `summary` and `contributions` with
  `mcp`, `cli` and `skills` identifier arrays.
- `compatibility` with `platforms`, `architectures`, nullable `minimum_host` and nullable
  `maximum_host`. Platforms are the manifest's explicit unique subset of `macos` and `windows`,
  defaulting to `['macos']` for legacy declarations. Architectures are a unique subset of `arm64`
  and `x86_64`; an empty array permits both. The minimum is inclusive and the maximum exclusive,
  following the host's semantic version precedence. Metadata support does not imply a shipped
  Windows App, gateway or provider.
- `dependencies`, containing manifest dependency IDs, command names, application locators, human
  setup instructions and nullable documentation URLs. These are prerequisites the user supplies, not
  instructions to install software automatically.
- Boolean `prerelease`, UTC `published_at`, boolean `withdrawn` and nullable `withdrawal_reason`. A
  withdrawn current version stays unavailable until a newer release supersedes it. An older version
  is never selected in its place.
- `assets`, sorted by numeric asset ID. Each archive carries `id`, `name`, `size` in bytes, `sha256`
  and its exact official browser download `url`, plus `compatibility` containing `platforms` and
  `architectures`. Each archive target must be a subset of the release-wide target.

Per-archive targets come from `[[compatibility.artifacts]]` in the exact tagged manifest. Each entry
supplies `name`, `platforms` and `architectures`; names match published archive assets exactly and
are unique ignoring case. A declared list must account for every published archive, and every
declared archive must exist. Windows declarations require this list. Without one, archives inherit
the legacy release target. Neither filenames nor native binary inspection can substitute for the
declaration. Installation independently re-fetches the tag and proves the selected target before
accepting the exact package bytes.

Schema 1 contains no asset target field and requires macOS release targets. The publisher accepts
such a seed, materializes each archive's already implied target, then advances generation to
schema 2. This preserves the release's immutable identity and withdrawal state; narrowing or
expanding an existing target is rejected. Schema downgrades are rejected. A client supporting only
schema 1 must retain its last known-good snapshot when presented with schema 2.

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
enumerates published release identities, selects the current versions by semantic precedence,
resolves each selected exact tag to a commit and reads the root `computer-mcp-plugin.toml` at that
commit. It checks the Git blob identity, tag/version agreement, manifest projection, release-owned
assets, uploaded state, size and SHA-256.

Every advertised archive is downloaded within bounded budgets. The generator reads the root manifest
directly from ZIP or tar, compares its bytes with the tagged manifest, and never extracts or
executes package code. It checks release, tag and asset identities again after downloading.
Non-archive receipt files are not advertised as installable archives. A selected release with no
complete verified archive fails generation; a draft is not advertised. Historical archives are
outside discovery scope and are not fetched. A broken current archive fails the whole generation and
preserves the previous snapshot, rather than selecting an older release. Equal-precedence versions
with different release identities are ambiguous and fail selection.

Existing package identities are immutable. Changing their tag commit, declaration, asset ID, name,
digest or size fails generation. Promoting a prerelease to the stable channel preserves the same
package identity. A current record can leave the snapshot only when a strictly newer version of the
same plugin and numeric repository supersedes it. Stable releases require stable successors;
prereleases can be superseded by either channel. This also applies when a client skips generations.
Missing releases, missing assets and network failures do not imply withdrawal or permit rollback.

To withdraw a version, add a record to the policy's `withdrawals` array:

```json
{
  "repository_id": 123,
  "release_id": 456,
  "reason": "A concise explanation for people selecting this version."
}
```

For a current version, the record must identify a previously verified or currently verifiable
release. The publisher retains its verified metadata and marks it withdrawn, including when the
upstream release has disappeared. A newer release supersedes that unavailable current version.
Policy withdrawal identities can remain as durable safety records after supersession, but they do
not add historical versions to discovery. An unknown release identity is rejected. A deleted
repository can be removed from the allowlist only with explicit withdrawals of its remaining current
releases. Removing a withdrawal does not silently restore a version; deliver a new release instead.
Published GitHub release files and tags remain immutable.

## Publication and failure behavior

Writers for one destination serialize across processes. Each writer reads the previous snapshot
after obtaining the lock, rebuilds the complete catalog, validates every record and only then
replaces the file atomically. No independent plugin job writes shared catalog records. Duplicate
events are idempotent; a complete reconciliation discovers releases even when their notification was
missed. A detected external edit aborts publication. File and directory synchronization make the
replacement durable; failures before replacement leave the previous bytes intact.

The committed canonical `public/plugins/index.json` on `master` is the durable generation authority.
Initialize it by generating and reviewing a complete verified snapshot, then committing it with the
publisher policy. Automation never uses a missing file as permission to reset generation, and never
restores authority from a CDN response, an Actions cache or an expiring artifact.

The official repository's `pages.yml` workflow reconciles hourly at minute 37, on `master` pushes
and through `workflow_dispatch`. One `pages` concurrency group covers generation through deployment;
active runs are not cancelled. Each run checks out current `master` after entering the group and
verifies its seed before requesting release metadata. It always scans every admitted repository, so
missed notifications and replaced pending runs are repaired by the next successful reconciliation.

After generation, the workflow validates and tests the complete site. The publication helper checks
the catalog successor, exact built index bytes and unchanged source, then commits only the new index
as a child of the checked-out commit. It uses a normal fast-forward push, never a force push. A
concurrent source update rejects publication; the next run starts from current `master`. Identical
catalog content creates no commit. Unrelated local or staged changes are rejected and preserved.

Only then does Pages upload and deploy the complete artifact. Generation, validation or commit
failure prevents upload and preserves the deployed artifact. If deployment fails after the verified
index commit, the next run uses that committed generation and can deploy it without incrementing
generation. A local generated file alone does not deploy anything. Publisher tests also run in
read-only website CI, without contacting release sources.

The central build job uses its short-lived GitHub job token with `contents: write` to persist the
index; the deployment job has Pages and identity-token permissions. Plugin notification senders
should invoke `pages.yml` on `master` using `workflow_dispatch`, with Actions write access scoped to
this receiving repository. They do not need website Contents write access. Notification payloads
provide no metadata or policy overrides. Existing GitHub authentication is an operator input; this
repository does not create credentials. If notifications are unavailable, scheduled and manual
reconciliation still use the same complete verification path.

## Plugin release notifications

`.github/actions/notify-catalog` is the central composite action for notification senders. Pin it to
a reviewed full commit in each plugin's workflow. It requires Python 3 on the runner, creates a
short-lived installation token from its `client-id` and `private-key` inputs, and sends only
`{"ref":"master"}` to the fixed official `pages.yml` workflow. It cannot supply releases, replace
policy or select another ref. It neither checks out nor executes the plugin package.

The organization-owned catalog GitHub App is installed only on
`computer-mcp/computer-mcp.github.io`, with Actions write and mandatory Metadata read. Actions write
also permits other Actions administration in that repository; GitHub does not offer a
workflow-specific dispatch-only permission. The App has no website Contents write permission.
Disable its webhook and user OAuth flows; the sender only needs installation authentication.

Configure `CATALOG_APP_CLIENT_ID` as an Actions variable and `CATALOG_APP_PRIVATE_KEY` as an Actions
secret in each authorized official plugin repository. The composite action pins GitHub's token
action, explicitly scopes each token to the receiving repository and Actions write, and revokes the
token when the job finishes. GitHub also expires installation tokens after one hour. Neither the
private key nor token is written to artifacts or logs. A plugin's own `GITHUB_TOKEN` does not
provide this cross-repository authority. Missing or rejected authority fails notification visibly.

The organization owner controls the App and key rotation. Generate a replacement key, update the
five authorized sender secrets, verify a manual notification, then revoke the previous key.
Suspending the installation stops notification access immediately. Scheduled reconciliation in the
website continues independently. Key provisioning and rotation are explicit owner operations;
ordinary release jobs mint only temporary installation tokens.

Plugin workflows subscribe to published and edited releases, support manual retry, and expose a
reusable workflow for the final publication job. A release created with a repository job token does
not trigger ordinary release-event workflows: that publishing job must explicitly call notification
after making the accepted release public. Candidate creation and draft upload do not publish a
release and must not claim notification completion. GitHub documents these
[event chaining rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

The action uses the
[workflow dispatch API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event),
version `2026-03-10`. It validates the accepted run's numeric identity and exact official API/web
URLs, and returns `run-url`. This receipt proves only that GitHub accepted a central run; inspect
that run and the public index for generation, verification and Pages deployment success.

HTTP redirects are refused and response bodies are bounded to 16 KiB. Requests have a 20-second
socket timeout, at most three attempts and a 90-second retry budget; caller jobs impose a
three-minute limit. Transient failures honor supported server retry delays up to 30 seconds. Rate
limits without a supported explicit retry delay fail instead of retrying before reset or the
server's cooldown; retry the workflow later according to GitHub's rate-limit response.
Authentication/configuration failures are not retried. Errors never print credentials or remote
response bodies. A lost response may cause a duplicate request, which complete idempotent
reconciliation handles. A failed notification does not change the already published release; retry
the notification and let scheduled reconciliation recover missed events.

## Resource bounds and verification

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
