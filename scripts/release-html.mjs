import { validateRecord } from "./release.mjs";

export function renderReleaseLinks(html, record) {
  validateRecord(record);
  return html.replace(
    /<a\b([^>]*\bdata-release-link\b[^>]*)>([\s\S]*?)<\/a\s*>/g,
    (_link, attributes, label) => {
      if (record.version === null) {
        return '<span data-en="No releases yet">尚无发布版本</span>';
      }
      return `<a${attributes.replace(/href="[^"]*"/, `href="${record.release_url}"`)}>${label}</a>`;
    },
  );
}
