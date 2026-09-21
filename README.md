# Computer MCP product website

This repository owns the static product website published at
[computer-mcp.github.io](https://computer-mcp.github.io/). Product code, architecture, operator
documentation, issues, and releases live in the
[main Computer MCP repository](https://github.com/computer-mcp/computer-mcp).

The site is intentionally independent from the Swift repository. It has its own static build,
accessibility checks, browser-behavior tests, link validation, and GitHub Pages deployment. It does
not use a custom domain.

## Local development

Use Node.js 22 or newer:

```sh
npm ci
npm run dev
```

Run every repository gate:

```sh
npm run format:check
npm run check:html
npm run build
npm run check:links
npm run test:install
npm test
```

The production build is written to `dist/`. GitHub Pages deploys only that artifact from the
protected `main` branch.

`public/release.json` binds the deployed site artifact to the coordinated main repository source
commit and release tag. Update that record only as part of the indivisible two-repository release
batch.

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
