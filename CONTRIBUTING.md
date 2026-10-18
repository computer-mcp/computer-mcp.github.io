# Contributing

Keep website changes focused, accessible, and consistent with the current Computer MCP product
contract.

Before opening a pull request:

```sh
npm ci
npm run test:install
npm run check
```

Visual changes follow the organization
[DESIGN.md](https://github.com/computer-mcp/.github/blob/master/DESIGN.md); every visible string
needs both its Chinese text and its English `data-en` counterpart.

Changes to product positioning, capability status, security claims, connection support, or Codex
ownership must cite the corresponding implementation or documentation change in
[computer-mcp](https://github.com/computer-mcp/computer-mcp). This website does not own runtime
truth.

Use semantic HTML, preserve keyboard access and visible focus, respect reduced motion, and test both
configured Playwright viewports. Do not add a custom domain or a `CNAME` file without an explicit
repository decision.

Contributions are licensed under this repository's [LICENSE](LICENSE), FSL-1.1-ALv2.
