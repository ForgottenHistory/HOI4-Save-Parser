#!/usr/bin/env python3
"""List political parties for a country in a HOI4 save with popularity & leaders.

Public API:
    get_country_parties(save_text, tag, localizer, characters=None) -> list[dict] | None

Usage:
    python list_country_parties.py <save_path> <country_tag>
    python list_country_parties.py saves/WRA_1936_07_19_01.hoi4 WRA
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from localization import HOI4Localizer  # noqa: E402
from save_parsing import (  # noqa: E402
    parse_character_names,
    parse_country_parties,
    parse_country_name_hints,
)


def get_country_parties(
    save_text: str,
    tag: str,
    localizer: HOI4Localizer,
    characters: Optional[Dict[int, str]] = None,
) -> Optional[List[dict]]:
    """Return structured, localized party data for a country.

    Each entry has:
        {
            'id':             'paternal_autocrat',
            'popularity':     33.98,
            'is_default':     True,
            'is_ruling':      False,
            'short':          'SZR',
            'long_raw':       'Sovet ...\\n§LCouncil ...§!',
            'long_clean':     'Sovet ...',
            'leaders': [
                {'ideology': 'junta_subtype', 'character_id': 5511,
                 'name': 'Pavel Bermondt-Avalov'},
                ...
            ],
        }

    Sorted by popularity descending. Returns None if the country has no
    parsable politics block.

    `characters` is optional — if not provided, the function parses
    character names from the save itself. Pass an existing dict to skip
    that work when calling for many countries in a row.
    """
    parties = parse_country_parties(save_text, tag)
    if parties is None:
        return None
    if characters is None:
        characters = parse_character_names(save_text)

    hints = parse_country_name_hints(save_text)
    ruling_party = hints.get(tag, {}).get("ruling_party")

    entries: List[dict] = []
    for party_id, info in parties.items():
        # Use the inside-block name override key if present (KR cosmetic
        # overrides like CAN's social_liberal showing as GBR_social_liberal),
        # otherwise fall back to the conventional <TAG>_<party>_party keys.
        if info["name_override"] or info["long_name_override"]:
            short = localizer.get_localized_text(info["name_override"]) if info["name_override"] else ""
            long_raw = (
                localizer.get_localized_text(info["long_name_override"])
                if info["long_name_override"] else ""
            )
            long_clean = localizer._clean_display_string(long_raw)
            # Treat cleaned-key fallbacks as missing for these too.
            if info["name_override"] and info["name_override"] not in localizer.translations:
                short = ""
            if info["long_name_override"] and info["long_name_override"] not in localizer.translations:
                long_raw = ""
                long_clean = ""
        else:
            names = localizer.get_party_names(tag, party_id)
            short = names["short"]
            long_raw = names["long_raw"]
            long_clean = names["long_clean"]

        leaders = [
            {
                "ideology": L["ideology"],
                "character_id": L["character_id"],
                "name": characters.get(L["character_id"]),
            }
            for L in info["leaders"]
        ]

        entries.append({
            "id": party_id,
            "popularity": info["popularity"],
            "is_default": info["is_default"],
            "is_ruling": party_id == ruling_party,
            "short": short,
            "long_raw": long_raw,
            "long_clean": long_clean,
            "leaders": leaders,
        })

    entries.sort(key=lambda e: e["popularity"], reverse=True)
    return entries


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

    print("Loading KR-aware localization ...")
    import contextlib
    import io
    loc = HOI4Localizer()
    with contextlib.redirect_stdout(io.StringIO()):
        loc.load_all_files()

    print("Parsing characters and parties ...")
    parties = get_country_parties(save_text, tag, loc)
    if parties is None:
        print(f"No politics block found for tag {tag}")
        sys.exit(2)

    hints = parse_country_name_hints(save_text)
    h = hints.get(tag, {})
    country_name = loc.get_country_display_name(
        tag, cosmetic_tag=h.get("cosmetic_tag"), ruling_party=h.get("ruling_party")
    )

    print()
    print(f"==== {tag}: {country_name} ====")
    print(f"Parties: {len(parties)} (ruling: {h.get('ruling_party') or '?'})")
    print()
    print(f"  {'%':>6}  {'ID':25}  {'SHORT':12}  NAME")
    for p in parties:
        marker = "*" if p["is_ruling"] else " "
        leader_str = ""
        if p["leaders"]:
            first = p["leaders"][0]
            leader_str = f"  — {first['name']}" if first["name"] else f"  — id:{first['character_id']}"
        print(
            f"{marker} {p['popularity']:6.2f}  {p['id']:25}  "
            f"{p['short']:12}  {p['long_clean']}{leader_str}"
        )


if __name__ == "__main__":
    main()
