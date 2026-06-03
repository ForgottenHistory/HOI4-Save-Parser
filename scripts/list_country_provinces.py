#!/usr/bin/env python3
"""List every province owned by a country in a HOI4 save, grouped by state.

Public API:
    get_country_provinces(save_text, tag) -> {state_id: {province_ids}}
        (re-exported from map_data — same function name)

Usage:
    python list_country_provinces.py <save_path> <country_tag>
    python list_country_provinces.py saves/WRA_1936_07_19_01.hoi4 WRA
    python list_country_provinces.py saves/CAN_1946_05_28_24.hoi4 CAN --verbose
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from localization import HOI4Localizer  # noqa: E402
from map_data import get_country_provinces  # noqa: E402
from save_parsing import parse_country_name_hints  # noqa: E402


def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    args = [a for a in args if a not in ("--verbose", "-v")]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    save_path = Path(args[0])
    tag = args[1].upper()

    if not save_path.exists():
        print(f"Save not found: {save_path}")
        sys.exit(1)

    print(f"Reading {save_path.name} ...")
    save_text = save_path.read_text(encoding="utf-8", errors="ignore")

    print("Resolving playset map data and ownership ...")
    states = get_country_provinces(save_text, tag)
    if not states:
        print(f"{tag} owns no states (or no country block found)")
        sys.exit(2)

    print("Loading KR-aware localization ...")
    import contextlib
    import io
    loc = HOI4Localizer()
    with contextlib.redirect_stdout(io.StringIO()):
        loc.load_all_files()

    hints = parse_country_name_hints(save_text)
    h = hints.get(tag, {})
    country_name = loc.get_country_display_name(
        tag, cosmetic_tag=h.get("cosmetic_tag"), ruling_party=h.get("ruling_party")
    )

    total_provs = sum(len(p) for p in states.values())

    print()
    print(f"==== {tag}: {country_name} ====")
    print(f"States: {len(states)}    Provinces: {total_provs}")
    print()
    # Sort by state ID for predictable output. Could sort by province count
    # if you want capitals-first, but state-id is more useful for cross-
    # referencing the state files.
    for sid in sorted(states):
        provs = states[sid]
        state_name = loc.translations.get(f"STATE_{sid}") or f"State {sid}"
        print(f"  {sid:5}  {state_name:35}  {len(provs):4} provinces")
        if verbose:
            # Wrap province IDs in groups of 12 per line so wide states stay
            # readable. The IDs themselves are just integers; no names.
            sorted_provs = sorted(provs)
            for i in range(0, len(sorted_provs), 12):
                chunk = sorted_provs[i:i + 12]
                print(f"           {' '.join(f'{p:>5}' for p in chunk)}")


if __name__ == "__main__":
    main()
