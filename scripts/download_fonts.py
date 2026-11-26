#!/usr/bin/env python3
"""Descarga las fuentes OFL usadas por los presets de subtítulos."""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "assets" / "fonts"

# familia -> (carpeta, [(peso, nombre_archivo)], familia_de_google_fonts_para_ofl)
FAMILIES = {
    "Montserrat": ("montserrat", [(700, "Montserrat-Bold"), (800, "Montserrat-ExtraBold"), (900, "Montserrat-Black")]),
    "Poppins": ("poppins", [(700, "Poppins-Bold"), (800, "Poppins-ExtraBold"), (900, "Poppins-Black")]),
    "Anton": ("anton", [(400, "Anton-Regular")]),
    "Bebas Neue": ("bebas-neue", [(400, "BebasNeue-Regular")], "bebasneue"),
    "League Spartan": (
        "league-spartan",
        [(700, "LeagueSpartan-Bold"), (900, "LeagueSpartan-Black")],
        "leaguespartan",
    ),
    "Inter": ("inter", [(400, "Inter-Regular"), (600, "Inter-SemiBold"), (700, "Inter-Bold")]),
}

CSS_URL = "https://fonts.googleapis.com/css?family={family}:{weights}"
OFL_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}/OFL.txt"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def ttf_urls(family: str, weights: list[int]) -> dict[int, str]:
    css = fetch(CSS_URL.format(family=family.replace(" ", "+"), weights=",".join(map(str, weights))))
    blocks = re.findall(r"font-weight: (\d+);\s*src: url\(([^)]+)\)", css.decode())
    return {int(weight): url for weight, url in blocks}


def main() -> None:
    for family, (folder, files, *slug) in FAMILIES.items():
        target = DEST / folder
        target.mkdir(parents=True, exist_ok=True)
        weights = [weight for weight, _ in files]
        urls = ttf_urls(family, weights)
        for weight, name in files:
            path = target / f"{name}.ttf"
            path.write_bytes(fetch(urls[weight]))
            print(f"{path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
        google_slug = slug[0] if slug else folder
        (target / "OFL.txt").write_bytes(fetch(OFL_URL.format(slug=google_slug)))
        print(f"{target.relative_to(ROOT)}/OFL.txt")


if __name__ == "__main__":
    main()
