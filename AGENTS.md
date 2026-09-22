# Website agent guide

- Read `DESIGN.md` before visual, branding or landing-page composition changes. It is the approved
  design baseline; reuse the current tokens and source assets.
- Apply the user's requested scope while preserving the established identity for unrelated areas.
  Routine fixes and copy updates follow the same baseline.
- `README.md` owns local development; `CONTRIBUTING.md` owns contribution checks.
- Main Computer MCP documentation owns runtime, permission and capability facts. Keep the website's
  claims aligned with those sources.
- For product release metadata, use `scripts/release.mjs` and the release update/check commands in
  `README.md`. `public/release.json` is generated from the official delivered asset.
- Keep current visual rules in `DESIGN.md` and asset fingerprints in `public/brand/SHA256SUMS`.
  Update matching references when an accepted visual change alters the baseline.
