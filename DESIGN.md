# Computer MCP website design

Status: approved product design baseline.

This file owns the website's visual identity and composition. `src/styles.css` implements its tokens
and responsive rules. Product behavior remains owned by the main Computer MCP repository.
`README.md` owns website development and build instructions; `Assets/Brand/README.md` in the main
repository owns asset usage.

## Identity and message

- Product and public attribution: **Computer MCP**, the organization name.
- Primary Chinese message: **让 ChatGPT，用上你的本机工具。**
- English equivalent: **Let ChatGPT use your local tools.**
- Supporting brand line: **Your tools. One conversation.** / **你的工具，一个对话。**
- CLI, Codex, MCP and Skills are parallel ways to connect local capabilities.
- Explain tasks first, then prerequisites, permissions and capability maturity.
- The homepage is Chinese by default and provides a complete English switch.

## Visual character

Graphite surfaces, silver-white type, neutral secondary text, system fonts and precise spacing
create the product's restrained appearance. Typography and working UI establish the hierarchy. The
computer-window symbol provides the shared visual identity.

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
4. Workflow explanation, host permissions and native Codex boundaries.
5. Three setup steps and an actionable first read-only tool call.
6. FAQ, closing message, organization footer and project links.

The standard desktop content width is capped at 1180px with 112px section spacing. The current
breakpoints are 900px, 780px and 370px. Mobile content uses 24px side margins, reduced to 16px on
the narrowest screens. Feature, trust and setup columns stack while the four short capability
selectors remain peers.

Controls retain visible focus, meaningful selected states, keyboard operation and reduced-motion
support. Body copy, setup links and FAQ remain live HTML.

## Assets and visual references

- `public/brand/mark.png`: approved window symbol; 1254 × 1254 opaque PNG.
- `public/brand/social.png`: approved share card; 1729 × 910 opaque PNG.
- `public/brand/SHA256SUMS`: content fingerprints for those exact source assets. Verify from that
  directory with `shasum -a 256 -c SHA256SUMS`.
- `public/og-image.png` is built from the share-card source; dimensions in Open Graph metadata match
  the source. Preserve aspect ratio and its surrounding space.
- [Desktop reference](Design/References/desktop.png): 1488 × 1058, Chinese hero, default CLI panel,
  no browser chrome.
- [Mobile reference](Design/References/mobile.png): 393 × 851, Chinese hero, default CLI panel,
  keyboard focus visible on the closed menu button.

These are rendered website references. They guide comparison at the same size, language and state.
The screenshots cover the hero; current semantic HTML and this specification define the remaining
page structure.

## Maintaining the baseline

Routine copy updates, bug fixes and accessibility improvements use this identity. Keep shared
styling in the existing tokens and components. A request for a new visual direction changes the
baseline only within the user's stated scope.

When an accepted change affects identity, core composition or source artwork, update this file, the
relevant references and asset fingerprints together. Keep the website and main repository's shared
assets synchronized. Existing brand requirements remain in force for unrelated edits.

Validate affected interactions and both desktop/mobile layouts according to `CONTRIBUTING.md`. Use a
Git commit as the recoverable version boundary; this specification and the fingerprints guide review
but do not prevent edits.
