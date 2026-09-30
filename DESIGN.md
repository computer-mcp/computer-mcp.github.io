# Computer MCP website design

Status: approved website application baseline.

This file owns website-specific composition and responsive application. `src/styles.css` implements
the layout. The main repository's
[Product Identity](https://github.com/computer-mcp/computer-mcp/blob/master/Documentation/Architecture/ProductIdentity.md)
owns product meaning;
[BRAND.md](https://github.com/computer-mcp/computer-mcp/blob/master/Assets/Brand/BRAND.md) and
[brand.json](https://github.com/computer-mcp/computer-mcp/blob/master/Assets/Brand/brand.json) own
shared identity. `README.md` owns website development and build instructions.

## Identity and message

- Product and public attribution: **Computer MCP**, the organization name.
- Primary Chinese message: **让 ChatGPT，用上你的本机工具。**
- English equivalent: **Let ChatGPT use your local tools.**
- Import exact stable copy and delivery through `public/brand/brand.lock.json`.
- Direct, Local, Composable, Multi-computer and Governed frame the product.
- CLI, MCP, Skills, Computer Use and optional Codex connect local capabilities.
- Explain tasks first, then prerequisites, permissions and capability maturity.
- The homepage is Chinese by default and provides a complete English switch.

## Visual character

Graphite surfaces, silver-white type, neutral secondary text, system fonts and precise spacing
create the product's restrained appearance. Typography and working UI establish the hierarchy. The
rounded-display symbol provides the shared visual identity.

## Tokens

| Role                     | CSS token          | Value     |
| ------------------------ | ------------------ | --------- |
| Page                     | `--background`     | `#171819` |
| Raised surface           | `--surface`        | `#202123` |
| Active surface           | `--surface-active` | `#2b2d30` |
| Main text                | `--text`           | `#f5f5f7` |
| Secondary text           | `--muted`          | `#acafb5` |
| Dividers                 | `--line`           | `#3b3d41` |
| Links and keyboard focus | `--link`           | `#a7cfff` |

The font stack is `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `PingFang SC`,
`Hiragino Sans GB`, then `sans-serif`. Body text starts at 16px with 1.65 line height. Display text
uses the system font with deliberate line breaks; the current desktop headline is capped at 84px.
Text must remain readable in both languages and at narrow widths.

## Page composition

1. Compact sticky navigation with the window mark, product name, core links, language switch and Get
   started action. Mobile navigation is collapsible.
2. Centered hero: two-line promise, supporting copy, one primary capsule action, GitHub link and a
   concise prerequisites line.
3. Four equally weighted capability tabs: CLI, Codex, MCP and Skills. The selected tab exposes a
   labelled task example, explanation and working reference link.
4. Workflow explanation and independent host connections, followed by host permissions and native
   Codex boundaries.
5. A dated, sourced comparison of Computer MCP, Dots and Codex Remote by job and execution model.
6. Three setup steps and an actionable first read-only tool call.
7. FAQ, closing promise, organization footer and project links.

The standard desktop content width is capped at 1180px with 112px section spacing. The current
breakpoints are 900px, 780px and 370px. Mobile content uses 24px side margins, reduced to 16px on
the narrowest screens. Feature, trust and setup columns stack while the four short capability
selectors remain peers.

Controls retain visible focus, meaningful selected states, keyboard operation and reduced-motion
support. Body copy, setup links and FAQ remain live HTML.

## Assets and visual references

- `public/brand/mark.svg` and `mark.png`: canonical master mark; PNG is 1024 × 1024.
- `public/brand/favicon.png` and `apple-touch-icon.png`: supplied 32 px and 180 px icon exports.
- `public/brand/social-en.png` and `social-zh-CN.png`: canonical 1280 × 640 share cards.
- `public/brand/brand.lock.json`: imported stable copy, brand revision and file digests. Run
  `npm run brand:check` to verify the locked delivery without a main-repository checkout.
- Open Graph points to the English share card. `public/og-image.png` is a byte-identical
  compatibility copy generated at build time. Preserve the supplied aspect ratio and clear space.
- [Desktop reference](Design/References/desktop.png): 1488 × 1058, Chinese hero, default CLI panel,
  no browser chrome.
- [Mobile reference](Design/References/mobile.png): 393 × 851, Chinese hero, default CLI panel,
  keyboard focus visible on the closed menu button.

These are rendered website references. They guide comparison at the same size, language and state.
The screenshots cover the hero; current semantic HTML and this specification define the remaining
page structure.

After building, start `npm run preview -- --host 127.0.0.1` and run `npm run design:references` to
refresh these exact viewport/state references.

## Maintaining the baseline

Routine copy updates, bug fixes and accessibility improvements follow the main brand contract. Keep
website styling in the existing tokens and components.

When a canonical identity revision is accepted, import its assets and lock using the main
repository's `Scripts/brand.py sync`. Update affected website composition rules and rendered
references together. Website edits do not redefine the master brand.

Validate affected interactions and both desktop/mobile layouts according to `CONTRIBUTING.md`. Use a
Git commit as the recoverable version boundary; this specification and the fingerprints guide review
but do not prevent edits.
