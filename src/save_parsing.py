"""Shared helpers for walking the plaintext HOI4 save structure.

The save is a textual key/value tree with brace-delimited blocks. Anything
that needs to drill into a specific country's data — focus history, ruling
party, cosmetic tag — has to find that country's block, which is non-trivial
because the same `\\n\\t<TAG>={` opener appears in unrelated places like
diplomatic-relation entries.
"""

from __future__ import annotations

import re
from typing import Dict, Optional


# Country tags in saves are 3-character A-Z0-9 codes; some mods use longer
# (KaiserreduX has 4-char like "BOTDE_x") but the top-level country tag in
# the save is consistently 3 chars in plaintext format.
_COUNTRY_TAG_RE = re.compile(r"\n\t([A-Z0-9]{3})=\{")
_RULING_PARTY_RE = re.compile(r'\bruling_party\s*=\s*"?(\w+)"?')
_COSMETIC_TAG_RE = re.compile(r'\bcosmetic_tag\s*=\s*"([^"]*)"')


def walk_block(text: str, open_pos: int) -> int:
    """Return index one past the matching ``}`` for an already-consumed ``{``.

    Caller must position `open_pos` just past the opening brace. Useful
    primitive for any "give me the body of this block" routine.
    """
    depth = 1
    i = open_pos
    n = len(text)
    while depth and i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return i


def find_country_block(save_text: str, tag: str) -> Optional[str]:
    """Return the body of the given country's top-level block.

    Country blocks look like ``\\n\\t<TAG>={ ... }`` and can span millions of
    characters. The same ``\\n\\t<TAG>={`` opener also appears inside
    diplomatic relation blocks (e.g. ``CAN={type=2 from_state=44 ...}``), so
    we guard by requiring the body to contain ``focus_tree=`` or
    ``ruling_party=`` — fields only real country blocks have.

    Returns the body string (everything between the ``{`` and matching
    ``}``), or None if the tag has no country block in this save.
    """
    header = f"\n\t{tag}=" + "{"
    for hm in re.finditer(re.escape(header), save_text):
        body_start = hm.end()
        body_end = walk_block(save_text, body_start)
        body = save_text[body_start:body_end - 1]
        if "focus_tree=" not in body and "ruling_party=" not in body:
            continue  # Diplomatic-relation entry or similar, not the country.
        return body
    return None


def parse_country_name_hints(save_text: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Extract per-country naming hints needed to resolve display names.

    Returns ``{tag: {'cosmetic_tag': <str or None>, 'ruling_party': <str or None>}}``
    for every country with a recognisable country block. The hints feed
    ``HOI4Localizer.get_country_display_name`` so dynamic / cosmetic name
    swaps (e.g. WHR with cosmetic_tag=WHR_BEL ruling as syndicalist becomes
    "the Belarusian Workers' Socialist Republic") render correctly.

    cosmetic_tag is None when the field is missing or set to "" (HOI4's
    "no override" value).
    """
    hints: Dict[str, Dict[str, Optional[str]]] = {}
    # Scan all top-level country block openers and accept the first whose
    # body looks like a real country (has focus_tree= or ruling_party=).
    for hm in _COUNTRY_TAG_RE.finditer(save_text):
        tag = hm.group(1)
        if tag in hints:
            continue
        body_start = hm.end()
        body_end = walk_block(save_text, body_start)
        body = save_text[body_start:body_end - 1]
        if "focus_tree=" not in body and "ruling_party=" not in body:
            continue
        cosmetic = None
        rp = None
        cm = _COSMETIC_TAG_RE.search(body)
        if cm and cm.group(1):
            cosmetic = cm.group(1)
        rpm = _RULING_PARTY_RE.search(body)
        if rpm:
            rp = rpm.group(1)
        hints[tag] = {"cosmetic_tag": cosmetic, "ruling_party": rp}
    return hints
