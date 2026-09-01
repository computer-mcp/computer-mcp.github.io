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
