#!/usr/bin/env python3
"""List land neighbors of a country in a HOI4 save.

Resolves the active playset's map data (provinces.bmp, definition.csv, and
history/states/) in mod load order, scans the province bitmap for adjacency,
and reports which country tags border the target.

Usage:
    python list_country_neighbors.py <save_path> <country_tag>
    python list_country_neighbors.py saves/WRA_1936_07_19_01.hoi4 WRA
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from localization import HOI4Localizer  # noqa: E402
from map_data import get_country_neighbors  # noqa: E402
from save_parsing import parse_country_name_hints  # noqa: E402


def _display(loc: HOI4Localizer, tag: str, hints: dict) -> str:
    h = hints.get(tag, {})
    return loc.get_country_display_name(
        tag,
        cosmetic_tag=h.get("cosmetic_tag"),
        ruling_party=h.get("ruling_party"),
    )


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    save_path = Path(sys.argv[1])
    tag = sys.argv[2].upper()

    if not save_path.exists():
        print(f"Save not found: {save_path}")
        sys.exit(1)

    print(f"Reading {save_path.name} ...")
    save_text = save_path.read_text(encoding="utf-8", errors="ignore")

    print("Resolving playset map data and scanning adjacency ...")
    neighbors = get_country_neighbors(save_text, tag)
    if not neighbors:
        print(f"No land neighbors found for {tag} (or {tag} owns no states)")
        sys.exit(2)

    print("Extracting per-country naming hints from save ...")
    hints = parse_country_name_hints(save_text)

    print("Loading KR-aware localization for display names ...")
    import contextlib
    import io
    loc = HOI4Localizer()
    with contextlib.redirect_stdout(io.StringIO()):
        loc.load_all_files()

    print()
    print(f"==== {tag}: {_display(loc, tag, hints)} ====")
    print(f"Land neighbors: {len(neighbors)}")
    for n in neighbors:
        print(f"  {n:4}  {_display(loc, n, hints)}")


if __name__ == "__main__":
    main()
