import { copyFile } from "node:fs/promises";
import sharp from "sharp";

const source = new URL("../public/brand/social.png", import.meta.url);
const destination = new URL("../public/og-image.png", import.meta.url);
const { width, height } = await sharp(source.pathname).metadata();
if (width !== 1729 || height !== 910) {
  throw new Error("Social image dimensions must match the website's Open Graph metadata.");
}
await copyFile(source, destination);
