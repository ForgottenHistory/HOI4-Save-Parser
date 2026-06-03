#!/usr/bin/env python3
"""List completed national focuses for a country from a HOI4 save file.

Public API:
    extract_focus_ids(save_text, tag) -> dict | None
    get_country_focuses(save_text, tag, localizer) -> dict | None

Usage:
    python list_country_focuses.py <save_path> <country_tag>
    python list_country_focuses.py saves/CAN_1946_05_28_24.hoi4 CAN
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from localization import HOI4Localizer


def _walk_block(text: str, open_pos: int) -> int:
    """Return index one past the matching `}` for a `{` already consumed at open_pos."""
    depth = 1
    i = open_pos
    n = len(text)
    while depth and i < n:
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    return i


def find_country_focus_block(save_text: str, tag: str) -> Optional[str]:
    """Return the inside of the country's focus block.

    The save's `countries` section contains entries like `\\n\\t<TAG>={ ... }`
    where the body can span millions of characters. Inside, the focus block
    appears as `\\n\\t\\tfocus={ ... }`. We locate the country block by its
    tab-indented header, brace-walk its full extent, then find the focus block
    within that range.

    Returns None if the tag isn't found; '' if the country exists but has no
    focus block (e.g. a country with no focus tree).
    """
    header = f'\n\t{tag}=' + '{'
    # Each country block opener appears exactly once in well-formed saves, but
    # be defensive: skip openers whose body lacks the expected country fields.
    for hm in re.finditer(re.escape(header), save_text):
        body_start = hm.end()
        body_end = _walk_block(save_text, body_start)
        body = save_text[body_start:body_end - 1]
        if 'focus_tree=' not in body and 'ruling_party=' not in body:
            continue  # Not the real country block (e.g. a relation entry).
        fm = re.search(r'\n\t\tfocus=\{', body)
        if not fm:
            return ''  # Country exists but has no focus block.
        f_start = fm.end()
        f_end = _walk_block(body, f_start)
        return body[f_start:f_end - 1]
    return None


def extract_focus_ids(save_text: str, tag: str) -> Optional[dict]:
    """Return raw focus IDs for a country, without localization.

    Returns {'completed': [id, ...], 'current': id_or_None} on success,
    or None if the country tag isn't present in the save.
    """
    block = find_country_focus_block(save_text, tag)
    if block is None:
        return None
    completed = re.findall(r'completed="([^"]+)"', block)
    current_m = re.search(r'current="([^"]+)"', block)
    return {
        "completed": completed,
        "current": current_m.group(1) if current_m else None,
    }


def get_country_focuses(save_text: str, tag: str, localizer: HOI4Localizer) -> Optional[dict]:
    """Return structured, localized focus data for a country.

    Shape:
        {
            'tag': 'CAN',
            'country_name': 'Kingdom of Canada',
            'completed': [{'id': ..., 'title': ..., 'description': ...}, ...],
            'current':    {'id': ..., 'title': ..., 'description': ...} | None,
        }

    Returns None if the country tag isn't present in the save.

    Descriptions come from `<focus_id>_desc` and are empty strings when no
    description exists. Raw HOI4 formatting codes (§L, §!, \\n, [GetX] tokens)
    are left intact; consumers can strip or render them as they prefer.
    """
    ids = extract_focus_ids(save_text, tag)
    if ids is None:
        return None

    def _entry(fid: str) -> dict:
        return {
            "id": fid,
            "title": localizer.get_localized_text(fid),
            "description": localizer.get_focus_description(fid),
        }

    return {
        "tag": tag,
        "country_name": localizer.get_country_name(tag),
        "completed": [_entry(fid) for fid in ids["completed"]],
        "current": _entry(ids["current"]) if ids["current"] else None,
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
    save_text = save_path.read_text(encoding='utf-8', errors='ignore')

    print("Loading KR-aware localization (this takes a few seconds) ...")
    import contextlib
    import io
    loc = HOI4Localizer()
    with contextlib.redirect_stdout(io.StringIO()):
        loc.load_all_files()
    print(f"  {len(loc.translations):,} translations loaded\n")

    result = get_country_focuses(save_text, tag, loc)
    if result is None:
        print(f"No focus block found for tag {tag}")
        sys.exit(2)

    print(f"==== {result['tag']}: {result['country_name']} ====")
    print(f"Completed focuses: {len(result['completed'])}")
    if result['current']:
        cur = result['current']
        print(f"In progress: {cur['id']}  ->  {cur['title']}")
    print()
    for i, focus in enumerate(result['completed'], 1):
        print(f"  {i:3}. {focus['id']:50}  {focus['title']}")
        if focus['description']:
            print(f"       {focus['description']}")
            print()


if __name__ == "__main__":
    main()
