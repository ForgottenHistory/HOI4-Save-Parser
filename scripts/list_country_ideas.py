#!/usr/bin/env python3
"""List active national ideas for a country in a HOI4 save.

Public API:
    get_country_ideas(save_text, tag, localizer, include_hidden=False)
        -> list[dict] | None

Usage:
    python list_country_ideas.py <save_path> <country_tag>
    python list_country_ideas.py saves/WRA_1936_07_19_01.hoi4 WRA --all
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from localization import HOI4Localizer  # noqa: E402
from save_parsing import (  # noqa: E402
    parse_country_ideas,
    parse_country_name_hints,
)


def get_country_ideas(
    save_text: str,
    tag: str,
    localizer: HOI4Localizer,
    include_hidden: bool = False,
) -> Optional[List[dict]]:
    """Return structured idea data for a country's active national ideas.

    Each entry: {id, name, name_clean, description, is_hidden}.
    Order matches save order (the order ideas were added in-game). Hidden
    ideas are filtered out by default.
    """
    ids = parse_country_ideas(save_text, tag)
    if ids is None:
        return None

    entries: List[dict] = []
    for idea_id in ids:
        d = localizer.get_idea_display(idea_id)
        if d["is_hidden"] and not include_hidden:
            continue
        entries.append({
            "id": idea_id,
            "name": d["name"],
            "name_clean": d["name_clean"],
            "description": d["description"],
            "is_hidden": d["is_hidden"],
        })
    return entries


def main():
    args = sys.argv[1:]
    include_hidden = "--all" in args
    args = [a for a in args if a != "--all"]
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

    print("Loading KR-aware localization ...")
    import contextlib
    import io
    loc = HOI4Localizer()
    with contextlib.redirect_stdout(io.StringIO()):
        loc.load_all_files()

    raw_ids = parse_country_ideas(save_text, tag)
    if raw_ids is None:
        print(f"No country block found for tag {tag}")
        sys.exit(2)

    entries = get_country_ideas(save_text, tag, loc, include_hidden=include_hidden)
    hints = parse_country_name_hints(save_text)
    h = hints.get(tag, {})
    country_name = loc.get_country_display_name(
        tag, cosmetic_tag=h.get("cosmetic_tag"), ruling_party=h.get("ruling_party")
    )
    hidden_count = sum(1 for i in raw_ids if loc.get_idea_display(i)["is_hidden"])

    print()
    print(f"==== {tag}: {country_name} ====")
    suffix = f" ({hidden_count} hidden; use --all to show)" if hidden_count and not include_hidden else ""
    print(f"Active national ideas: {len(entries)}{suffix}")
    print()
    for i, idea in enumerate(entries, 1):
        marker = " [hidden]" if idea["is_hidden"] else ""
        name = idea["name_clean"] or idea["id"]
        print(f"  {i:2}. {idea['id']:40}{marker}  {name}")
        if idea["description"]:
            print(f"      {idea['description']}")
            print()


if __name__ == "__main__":
    main()
