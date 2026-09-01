import { readFile } from "node:fs/promises";
import { join } from "node:path";
import sharp from "sharp";

const root = new URL("../", import.meta.url).pathname;
const source = join(root, "public", "og-image.svg");
const destination = join(root, "public", "og-image.png");
const svg = await readFile(source);

await sharp(svg, { density: 144 })
  .resize(1200, 630)
  .png({ compressionLevel: 9 })
  .toFile(destination);
