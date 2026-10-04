#!/usr/bin/env python3
"""Build and check the bundled web fonts.

update  subset the pinned OFL sources into src/fonts and rewrite the lock
        (requires fontTools and brotli:
        uv run --no-project --with fonttools --with brotli scripts/fonts.py update)
check   verify the lock, the committed files and the page text (standard library only)
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "src/fonts"
LOCK = FONTS / "fonts.lock.json"
CACHE = ROOT / ".cache/fonts"
PAGES = ["index.html", "guide/index.html", "src/main.js"]
GOOGLE_FONTS = "https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl"
LATIN = "U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2010-2027,U+2030-203A,U+2190-2193,U+2212,U+2215"
SOURCES = [
    {
        "file": "bricolage-grotesque.woff2",
        "family": "Bricolage Grotesque",
        "url": f"{GOOGLE_FONTS}/bricolagegrotesque/BricolageGrotesque%5Bopsz%2Cwdth%2Cwght%5D.ttf",
        "sha256": "413e7357809ddd12fd80a96a8a396de0e401638d4acd3cb3e37532f0472ac682",
        "unicodes": LATIN,
    },
    {
        "file": "jetbrains-mono.woff2",
        "family": "JetBrains Mono",
        "url": f"{GOOGLE_FONTS}/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
        "sha256": "48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda",
        "unicodes": LATIN,
    },
    {
        "file": "noto-sans-sc.woff2",
        "family": "Noto Sans SC",
        "url": f"{GOOGLE_FONTS}/notosanssc/NotoSansSC%5Bwght%5D.ttf",
        "sha256": "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da",
        "unicodes": "page",
        "weights": [400, 800],
    },
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def page_characters():
    """CJK characters and full-width punctuation used by the pages."""
    text = "".join((ROOT / name).read_text() for name in PAGES)
    return "".join(sorted({char for char in text if ord(char) >= 0x2E80}))


def source(font):
    path = CACHE / f"{font['sha256']}.ttf"
    if not path.is_file():
        CACHE.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(font["url"], timeout=120) as response:
            path.write_bytes(response.read())
    if sha256(path.read_bytes()) != font["sha256"]:
        path.unlink()
        sys.exit(f"Source digest mismatch: {font['family']}")
    return path


def update():
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    characters = page_characters()
    files = {}
    for font in SOURCES:
        ttf = TTFont(source(font))
        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.name_languages = ["*"]
        options.notdef_outline = True
        subsetter = subset.Subsetter(options)
        if font["unicodes"] == "page":
            subsetter.populate(text=characters)
        else:
            subsetter.populate(unicodes=subset.parse_unicodes(font["unicodes"]))
        subsetter.subset(ttf)
        if "weights" in font:
            low, high = font["weights"]
            ttf = instancer.instantiateVariableFont(ttf, {"wght": (low, high)})
        output = FONTS / font["file"]
        FONTS.mkdir(parents=True, exist_ok=True)
        ttf.flavor = "woff2"
        ttf.save(output)
        files[font["file"]] = sha256(output.read_bytes())
        print(f"{font['file']}: {output.stat().st_size // 1024} KiB")
    lock = {
        "schema_version": 1,
        "sources": {font["file"]: font["sha256"] for font in SOURCES},
        "files": files,
        "page_characters": characters,
    }
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n")


def check():
    lock = json.loads(LOCK.read_text())
    errors = []
    if lock.get("sources") != {font["file"]: font["sha256"] for font in SOURCES}:
        errors.append("Font sources changed; run the update command.")
    for name, expected in lock.get("files", {}).items():
        path = FONTS / name
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            errors.append(f"{name} differs from fonts.lock.json.")
    missing = sorted(set(page_characters()) - set(lock.get("page_characters", "")))
    if missing:
        errors.append(f"Noto Sans SC subset lacks {''.join(missing)}; run the update command.")
    print("\n".join(errors) or "Bundled fonts match their lock and the page text.")
    return 1 if errors else 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "update":
        update()
    elif command == "check":
        sys.exit(check())
    else:
        sys.exit(__doc__)
