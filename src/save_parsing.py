"""Shared helpers for walking the plaintext HOI4 save structure.

The save is a textual key/value tree with brace-delimited blocks. Anything
that needs to drill into a specific country's data — focus history, ruling
party, cosmetic tag — has to find that country's block, which is non-trivial
because the same `\\n\\t<TAG>={` opener appears in unrelated places like
diplomatic-relation entries.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# Country tags in saves are 3-character A-Z0-9 codes; some mods use longer
# (KaiserreduX has 4-char like "BOTDE_x") but the top-level country tag in
# the save is consistently 3 chars in plaintext format.
_COUNTRY_TAG_RE = re.compile(r"\n\t([A-Z0-9]{3})=\{")
_RULING_PARTY_RE = re.compile(r'\bruling_party\s*=\s*"?(\w+)"?')
_COSMETIC_TAG_RE = re.compile(r'\bcosmetic_tag\s*=\s*"([^"]*)"')
# Top-of-file player="TAG". Anchored to the start so we don't pick up the
# many `player=...` lines that appear deeper in the save (per-character,
# per-decision, etc.).
_PLAYER_TAG_RE = re.compile(r'^player="([A-Z0-9]{3})"', re.MULTILINE)
# Top-of-file date="YYYY.M.D.H". Same anchoring concern as player above —
# `date=` shows up deep in war/event/character blocks, but only the header
# date represents the current game state.
_GAME_DATE_RE = re.compile(r'^date="(\d{1,4})\.(\d{1,2})\.(\d{1,2})\.(\d{1,2})"', re.MULTILINE)


def get_player_tag(save_text: str) -> Optional[str]:
    """Return the single-player country tag from the save header, or None.

    HOI4 writes ``player="TAG"`` in the first few lines of every save. For
    multiplayer saves, ``player_countries={ TAG1={...} TAG2={...} }`` lists
    everyone — this helper covers the single-player case only.
    """
    m = _PLAYER_TAG_RE.search(save_text)
    return m.group(1) if m else None


def get_game_date(save_text: str) -> Optional[Dict[str, object]]:
    """Return the current in-game date from the save header.

    Shape: ``{'year', 'month', 'day', 'hour', 'raw'}`` or None if absent.

    HOI4 dates are ``YYYY.M.D.H`` (one-or-two-digit M/D/H, NOT zero-padded).
    The hour component runs 0..24 — yes, 24 not 23: HOI4 internally uses
    "1-indexed hours within the day" so the last tick of May 28 is
    ``1946.5.28.24`` rather than rolling to the next day. We surface the
    raw value rather than normalising; consumers comparing dates should
    treat hour 24 as "end of <day>".
    """
    m = _GAME_DATE_RE.search(save_text)
    if not m:
        return None
    return {
        "year":  int(m.group(1)),
        "month": int(m.group(2)),
        "day":   int(m.group(3)),
        "hour":  int(m.group(4)),
        "raw":   f"{m.group(1)}.{m.group(2)}.{m.group(3)}.{m.group(4)}",
    }


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


# ---------------------------------------------------------------------------
# Political parties
# ---------------------------------------------------------------------------

_IDEAS_BLOCK_RE = re.compile(r"\n\t\t\tideas=\{")
_PARTIES_BLOCK_RE = re.compile(r"\n\t\t\tparties=\{")
_PARTY_OPENER_RE = re.compile(r"\n\t\t\t\t([a-z_]+)=\{")
_POPULARITY_RE = re.compile(r"\bpopularity\s*=\s*([\d.]+)")
_DEFAULT_RE = re.compile(r"\bdefault\s*=\s*(yes|no)")
_PARTY_NAME_OVERRIDE_RE = re.compile(r'\bname\s*=\s*"([^"]+)"')
_PARTY_LONG_NAME_OVERRIDE_RE = re.compile(r'\blong_name\s*=\s*"([^"]+)"')
# country_leader array entries: each {ideology="..." character={ id=N type=T }}
_LEADER_ENTRY_RE = re.compile(
    r'ideology\s*=\s*"(?P<ideology>[^"]+)"\s*'
    r"character\s*=\s*\{\s*id\s*=\s*(?P<id>\d+)\s+type\s*=\s*\d+\s*\}",
    re.DOTALL,
)


def parse_country_parties(
    save_text: str, tag: str
) -> Optional[Dict[str, dict]]:
    """Return the parties block for a country, keyed by party id.

    Shape:
        {
            'paternal_autocrat': {
                'popularity': 33.98,
                'is_default': True,
                'name_override': 'GBR_paternal_autocrat_party' or None,
                'long_name_override': 'GBR_paternal_autocrat_party_long' or None,
                'leaders': [
                    {'ideology': 'junta_subtype', 'character_id': 5511},
                    ...
                ],
            },
            ...
        }

    Returns None if the country has no parsable politics.parties block.

    The name overrides are loc keys, not display strings — the localizer
    resolves them. They appear when KR uses a cosmetic system to display
    a different party name (e.g. CAN's social_liberal showing as the
    British Liberal Party while CAN is part of the Empire).
    """
    body = find_country_block(save_text, tag)
    if body is None:
        return None
    pm = _PARTIES_BLOCK_RE.search(body)
    if not pm:
        return None
    block_start = pm.end()
    block_end = walk_block(body, block_start)
    parties_block = body[block_start:block_end - 1]

    result: Dict[str, dict] = {}
    for opener in _PARTY_OPENER_RE.finditer(parties_block):
        party_id = opener.group(1)
        pb_start = opener.end()
        pb_end = walk_block(parties_block, pb_start)
        pbody = parties_block[pb_start:pb_end - 1]

        pop_m = _POPULARITY_RE.search(pbody)
        popularity = float(pop_m.group(1)) if pop_m else 0.0
        default_m = _DEFAULT_RE.search(pbody)
        is_default = default_m and default_m.group(1) == "yes"
        name_m = _PARTY_NAME_OVERRIDE_RE.search(pbody)
        long_m = _PARTY_LONG_NAME_OVERRIDE_RE.search(pbody)

        leaders = [
            {"ideology": m.group("ideology"), "character_id": int(m.group("id"))}
            for m in _LEADER_ENTRY_RE.finditer(pbody)
        ]

        result[party_id] = {
            "popularity": popularity,
            "is_default": bool(is_default),
            "name_override": name_m.group(1) if name_m else None,
            "long_name_override": long_m.group(1) if long_m else None,
            "leaders": leaders,
        }
    return result


# ---------------------------------------------------------------------------
# Character names
# ---------------------------------------------------------------------------

# Character entries look like:
#   id={ id=70894 type=73 }
#     token="WRA_ilya_polyakov"
#     name="Ilya Polyakov"
#     country="WRA"
# We scan specifically for type=73 (the character type) — the same numeric
# ID is reused for equipment (type=70), organizations (type=79), research
# projects (type=86) etc., and matching those would pull unrelated `name=`
# fields like equipment template names.
_CHARACTER_NAME_RE = re.compile(
    r'\bid=(\d+)\s+type=73\s*\}'          # id=70894 type=73 }
    r'(?:\s*token="[^"]*")?'              # optional token (usually present)
    r'\s*name="([^"]+)"'                  # name="Ilya Polyakov"
)


def parse_character_names(save_text: str) -> Dict[int, str]:
    """Return ``{character_id: name}`` for every character in the save.

    Scans the whole save once. KR saves with ~70k characters this completes
    in well under a second.
    """
    return {
        int(m.group(1)): m.group(2)
        for m in _CHARACTER_NAME_RE.finditer(save_text)
    }


# ---------------------------------------------------------------------------
# National ideas
# ---------------------------------------------------------------------------

def parse_country_ideas(save_text: str, tag: str) -> Optional[List[str]]:
    """Return the list of active national-idea IDs for a country, in save order.

    The save stores them as a flat whitespace-separated list inside
    ``politics={ ... ideas={ ID1 ID2 ID3 ... } }``. We return raw IDs only —
    name/description resolution happens in the localizer layer, and category
    grouping (economy law / trade law / country idea / ...) would require
    parsing ``common/ideas/*.txt`` which we don't do.

    Returns None if the country has no parsable country block.
    """
    body = find_country_block(save_text, tag)
    if body is None:
        return None
    bm = _IDEAS_BLOCK_RE.search(body)
    if not bm:
        # Country exists but has no ideas block — extremely unusual but
        # treat as "no ideas active" rather than "country missing".
        return []
    block_start = bm.end()
    block_end = walk_block(body, block_start)
    inner = body[block_start:block_end - 1]
    # Just split on whitespace; idea IDs are bare identifiers.
    return inner.split()
