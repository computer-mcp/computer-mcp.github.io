# Computer MCP product website

This repository owns the static product website published at
[computer-mcp.github.io](https://computer-mcp.github.io/). Product code, architecture, operator
documentation, issues, and releases live in the
[main Computer MCP repository](https://github.com/computer-mcp/computer-mcp).

The site is intentionally independent from the Swift repository. It has its own static build,
accessibility checks, browser-behavior tests, link validation, and GitHub Pages deployment. It does
not use a custom domain.

## Local development

Use Node.js 22 or newer and Python 3.11 or newer:

```sh
npm ci
npm run dev
```

Run every repository gate:

```sh
npm run catalog:check-policy
npm run format:check
npm run check:html
npm run build
npm run check:links
npm run test:install
npm test
```

The production build is written to `dist/`. GitHub Pages deploys only that artifact from the
official repository's `main` branch after validation and catalog reconciliation.

`public/release.json` binds the deployed site to the product's delivered commit and release tag. The
private website package version describes this build project, not the product version. After the
main repository publishes an accepted release, run `npm run release:update -- vX.Y.Z` to import its
`release.json` asset. The importer verifies the official repository, public stable release, tag
commit and GitHub asset digest; it refuses version regressions and changed identities for an
existing version. It never derives a release from an installed App or local source checkout. Commit
the generated record with the website delivery.

`npm run release:check` checks the local record without changing it.
`npm run release:verify-public -- vX.Y.Z` also compares it with the official public asset.
Historical releases without a delivery-record asset retain their existing record until the next
product delivery. Tests read the record rather than maintain another product-version constant.

The plugin catalog publisher generates a separate versioned snapshot of verified official plugin
releases. Run `npm run catalog:update -- --use-gh-auth` to produce `public/plugins/index.json` using
existing GitHub CLI authentication, or provide `GH_TOKEN`/`GITHUB_TOKEN` in the process environment.
The publisher also works without authentication within GitHub's public API limits. It downloads and
verifies release archives without running package code. `npm run catalog:check-policy` and
`npm run catalog:test` run offline; `npm run catalog:check` validates a generated snapshot. No
plugin catalog snapshot is currently shipped by this website. Automatic publication requires an
initial complete verified snapshot committed to `main`; until then, Pages publication fails before
upload and preserves the deployed site. Subsequent runs reconcile hourly, on source pushes and on
manual workflow dispatch, persist changed generations and deploy one complete artifact. See
[the plugin catalog contract](docs/plugin-catalog.md) for provenance, withdrawals, resource bounds,
atomic updates and installation trust.

## Content boundaries

- Keep claims aligned with behavior demonstrated in the main repository.
- Label advanced Codex orchestration as experimental.
- Present official Codex Remote as the preferred first-party choice for ordinary remote Codex
  control.
- Do not add testimonials, customer logos, usage statistics, or compatibility claims without
  verifiable evidence.
- Keep the security model explicit: gateway policy decides whether a capability is available;
  consent decides whether an allowed higher-risk action may proceed now.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change.

## Brand and copy

[DESIGN.md](DESIGN.md) is the approved website design baseline. It records the positioning, tokens,
composition, shared assets, responsive behavior and rendered reference images. Read it before
changing the visual identity.

The homepage leads with “Let ChatGPT use your local tools” and gives CLI, Codex, MCP and Skills
equal placement. Main-repository documentation owns capability and permission facts; website copy
follows that contract.

`npm run assets:build` checks the share-card dimensions and copies the source to
`public/og-image.png`. Verify the approved source images from `public/brand/` with
`shasum -a 256 -c SHA256SUMS`. Keep shared assets synchronized with the main repository's
`Assets/Brand/` directory.
