import { defineConfig } from "vite";
import { readFileSync } from "node:fs";
import { renderReleaseLinks } from "./scripts/release-html.mjs";

export default defineConfig({
  base: "/",
  plugins: [
    {
      name: "release-links",
      transformIndexHtml(html) {
        const record = JSON.parse(readFileSync(new URL("./public/release.json", import.meta.url)));
        return renderReleaseLinks(html, record);
      },
    },
  ],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        main: "index.html",
        guide: "guide/index.html",
      },
    },
  },
});
