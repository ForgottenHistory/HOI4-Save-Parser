#!/usr/bin/env python3
"""Show a country's current ruling party and leader in a HOI4 save.

A focused one-call view that composes existing primitives. For the full
party breakdown use list_country_parties; this script just answers
"who's in charge of <tag>?".

Public API:
    get_country_leader(save_text, tag, localizer,
                       characters=None, hints=None, parties=None) -> dict | None

Usage:
    python list_country_leader.py <save_path> <country_tag>
    python list_country_leader.py saves/WRA_1936_07_19_01.hoi4 WRA
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Reach into scripts/ for the parties composer rather than re-implementing
# the loc-key-vs-override resolution. Keeps a single source of truth.
sys.path.insert(0, str(Path(__file__).parent))

from list_country_parties import get_country_parties  # noqa: E402
from localization import HOI4Localizer  # noqa: E402
from save_parsing import (  # noqa: E402
    parse_character_names,
    parse_country_name_hints,
)


def get_country_leader(
    save_text: str,
    tag: str,
    localizer: HOI4Localizer,
    characters: Optional[Dict[int, str]] = None,
    hints: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
    parties: Optional[list] = None,
) -> Optional[dict]:
    """Return the ruling party and current leader for a country.

    Shape::

        {
            'tag':                'WRA',
            'country_name':       'The Western Russian Volunteer Army',
            'ruling_party_id':    'paternal_autocrat',
            'ruling_party_short': 'SZR',
            'ruling_party_long':  'Sovet Zapadnoy Rossii - ...',
            'leader_id':          5511,
            'leader_name':        'Pavel Bermondt-Avalov',
            'leader_ideology':    'junta_subtype',
        }

    Returns None if the country has no parsable politics block.

    The `characters`, `hints`, and `parties` params let callers iterating
    over many countries reuse a single full-save parse instead of paying
    for it per call.

    Edge cases:
    - If the ruling-party ID from the hints doesn't appear in the parties
      table (rare; possible in mid-event states), we fall back to the
      most-popular party so the consumer always sees *some* answer.
    - If the ruling party has no leaders array (also rare), leader fields
      come back as None rather than missing keys.
    """
    if hints is None:
        hints = parse_country_name_hints(save_text)
    h = hints.get(tag, {})

    if characters is None:
        characters = parse_character_names(save_text)

    if parties is None:
        parties = get_country_parties(save_text, tag, localizer, characters=characters)
    if parties is None:
        return None

    ruling_id = h.get("ruling_party")
    ruling = next((p for p in parties if p["id"] == ruling_id), None)
    if ruling is None and parties:
        # Hints disagree with the party list — pick the most popular party
        # so we still return something useful instead of None.
        ruling = parties[0]

    if ruling is None:
        return None

    first_leader = ruling["leaders"][0] if ruling["leaders"] else None

    country_name = localizer.get_country_display_name(
        tag,
        cosmetic_tag=h.get("cosmetic_tag"),
        ruling_party=h.get("ruling_party"),
    )

    return {
        "tag": tag,
        "country_name": country_name,
        "ruling_party_id": ruling["id"],
        "ruling_party_short": ruling["short"],
        "ruling_party_long": ruling["long_clean"],
        "leader_id": first_leader["character_id"] if first_leader else None,
        "leader_name": first_leader["name"] if first_leader else None,
        "leader_ideology": first_leader["ideology"] if first_leader else None,
    }


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

    info = get_country_leader(save_text, tag, loc)
    if info is None:
        print(f"No politics block found for {tag}")
        sys.exit(2)

    print()
    print(f"==== {info['tag']}: {info['country_name']} ====")
    print(f"Ruling party:    {info['ruling_party_long']} ({info['ruling_party_short']})")
    print(f"Party ideology:  {info['ruling_party_id']}")
    leader = info["leader_name"] or f"(unknown — id {info['leader_id']})"
    print(f"Leader:          {leader}")
    if info["leader_ideology"]:
        print(f"Leader ideology: {info['leader_ideology']}")


if __name__ == "__main__":
    main()
