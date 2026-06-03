#!/usr/bin/env python3
"""List completed national focuses for a country from a HOI4 save file.

Reads the raw plaintext save, finds the target country's focus block, extracts
every `completed="ID"` entry, and prints each with its KR-aware localized name.

Usage:
    python list_country_focuses.py <save_path> <country_tag>
    python list_country_focuses.py saves/CAN_1946_05_28_24.hoi4 CAN
"""

import re
import sys
from pathlib import Path

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


def find_country_focus_block(save_text: str, tag: str) -> str | None:
    """Return the inside of the country's focus block.

    The save's `countries` section contains entries like `\\n\\t<TAG>={ ... }`
    where the body can span millions of characters. Inside, the focus block
    appears as `\\n\\t\\tfocus={ ... }`. We locate the country block by its
    tab-indented header, brace-walk its full extent, then find the focus block
    within that range.
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
            return ''  # Country exists but has no focus block (no focus tree).
        f_start = fm.end()
        f_end = _walk_block(body, f_start)
        return body[f_start:f_end - 1]
    return None


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

    block = find_country_focus_block(save_text, tag)
    if block is None:
        print(f"No focus block found for tag {tag}")
        sys.exit(2)

    completed = re.findall(r'completed="([^"]+)"', block)
    current_m = re.search(r'current="([^"]+)"', block)
    current = current_m.group(1) if current_m else None

    print(f"Loading KR-aware localization (this takes a few seconds) ...")
    loc = HOI4Localizer()
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        loc.load_all_files()
    print(f"  {len(loc.translations):,} translations loaded\n")

    print(f"==== {tag}: {loc.get_country_name(tag)} ====")
    print(f"Completed focuses: {len(completed)}")
    if current:
        print(f"In progress: {current}  ->  {loc.get_localized_text(current)}")
    print()
    for i, fid in enumerate(completed, 1):
        name = loc.get_localized_text(fid)
        print(f"  {i:3}. {fid:50}  {name}")


if __name__ == "__main__":
    main()
