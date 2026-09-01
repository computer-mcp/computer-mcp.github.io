# Contributing

Keep website changes focused, accessible, and consistent with the current Computer MCP product
contract.

Before opening a pull request:

```sh
npm ci
npm run test:install
npm run check
```

Changes to product positioning, capability status, security claims, connection support, or Codex
ownership must cite the corresponding implementation or documentation change in
[computer-mcp](https://github.com/computer-mcp/computer-mcp). This website does not own runtime
truth.

Use semantic HTML, preserve keyboard access and visible focus, respect reduced motion, and test both
configured Playwright viewports. Do not add a custom domain or a `CNAME` file without an explicit
repository decision.
