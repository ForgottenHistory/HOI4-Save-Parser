"""Mod-aware HOI4 map data: province adjacency + state ownership + country neighbors.

This mirrors how the game itself resolves files when mods are stacked:
for any given relative path (e.g. ``map/provinces.bmp`` or
``history/states/1-Sichuan.txt``), the version that wins is the one shipped by
the highest-position enabled mod in the active playset, or the base game if no
mod overrides it.

The expensive bit (scanning ``provinces.bmp`` to build a province-adjacency
graph) takes ~0.5s for KR's 33MB map, so we do it on demand without caching.

Top-level entry point:
    get_country_neighbors(save_text, tag, hoi4_path=..., user_data_path=...)
        -> list[str]   land neighbor country tags, sorted

The intermediate functions are exposed for testing and for callers who want
to compose them differently:
    resolve_active_playset_mod_roots(user_data_path)
    resolve_file(relative_path, mod_roots, hoi4_path)
    parse_province_definitions(definition_csv_path) -> (color_to_id, sea_lake_ids)
    build_province_adjacency(provinces_bmp, color_to_id) -> {pid: {pid, ...}}
    parse_state_files(state_dir_resolver) -> (state_to_provinces, province_to_state)
    parse_state_owners(save_text) -> {state_id: owner_tag}
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Playset / mod-root resolution
# ---------------------------------------------------------------------------

def _default_user_dir() -> Path:
    env = os.environ.get("HOI4_USER_DIR")
    if env:
        return Path(env)
    return Path.home() / "Documents" / "Paradox Interactive" / "Hearts of Iron IV"


def resolve_active_playset_mod_roots(user_data_path: Optional[Path] = None) -> List[Path]:
    """Return the active playset's enabled mod root directories, in load order.

    Earlier entries are overridden by later ones, matching HOI4's file
    replacement rules. Returns [] if the launcher DB is missing or unreadable
    so callers fall back to base-game-only resolution.
    """
    user_data_path = user_data_path or _default_user_dir()
    db_path = user_data_path / "launcher-v2.sqlite"
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            active = conn.execute(
                "SELECT id FROM playsets WHERE isActive=1"
            ).fetchone()
            if not active:
                return []
            rows = conn.execute(
                """SELECT m.dirPath
                   FROM playsets_mods pm JOIN mods m ON m.id = pm.modId
                   WHERE pm.playsetId = ? AND pm.enabled = 1
                   ORDER BY pm.position""",
                (active[0],),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []

    return [Path(p) for (p,) in rows if p]


def resolve_file(
    relative_path: str,
    mod_roots: Iterable[Path],
    hoi4_path: Path,
) -> Optional[Path]:
    """Return the path the game would load for `relative_path`.

    Checks mods in reverse (last writer wins) so the first hit is the winner;
    falls back to base game. Returns None if no source ships this file.
    """
    rel = Path(relative_path)
    for mod_root in reversed(list(mod_roots)):
        candidate = mod_root / rel
        if candidate.is_file():
            return candidate
    base = hoi4_path / rel
    return base if base.is_file() else None


def resolve_dir_files(
    relative_dir: str,
    pattern: str,
    mod_roots: Iterable[Path],
    hoi4_path: Path,
) -> List[List[Path]]:
    """Return per-source file lists in load order, lowest priority first.

    For directories where the unit of replacement is the FILENAME (e.g.
    ``localisation/``), filename-keyed merging works. For ``history/states/``
    the unit of replacement is the **state ID**, and a mod can redefine
    state 13 in a totally different filename — so callers need ordered
    per-source visibility to deduplicate semantically.

    Returns a list like ``[base_game_files, mod1_files, mod2_files, ...]``,
    each inner list being all the files that source ships. Callers apply
    last-writer-wins on whatever key matters (filename, state id, etc.).
    """
    sources: List[List[Path]] = []
    base_dir = hoi4_path / relative_dir
    if base_dir.is_dir():
        sources.append(sorted(base_dir.glob(pattern)))
    for mod_root in mod_roots:
        mod_dir = mod_root / relative_dir
        if mod_dir.is_dir():
            sources.append(sorted(mod_dir.glob(pattern)))
    return sources


# ---------------------------------------------------------------------------
# Map data parsing
# ---------------------------------------------------------------------------

def parse_province_definitions(
    definition_csv: Path,
) -> Tuple[Dict[Tuple[int, int, int], int], Set[int]]:
    """Parse ``map/definition.csv`` into (color->id, set of sea/lake ids).

    The CSV is semicolon-separated: ``id;r;g;b;type;coastal;terrain;continent``.
    Type is one of ``land``, ``sea``, ``lake``, ``unknown``. We treat ``sea``
    and ``lake`` as impassable for land-neighbor purposes.
    """
    color_to_id: Dict[Tuple[int, int, int], int] = {}
    sea_lake: Set[int] = set()
    # Paradox CSVs are latin-1; tolerate stray bytes.
    with open(definition_csv, "r", encoding="latin-1") as f:
        next(f)  # header
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 5:
                continue
            try:
                pid = int(parts[0])
                color_to_id[(int(parts[1]), int(parts[2]), int(parts[3]))] = pid
            except ValueError:
                continue
            if parts[4] in ("sea", "lake"):
                sea_lake.add(pid)
    return color_to_id, sea_lake


def build_province_adjacency(
    provinces_bmp: Path,
    color_to_id: Dict[Tuple[int, int, int], int],
) -> Dict[int, Set[int]]:
    """Build {province_id: {neighbor_id, ...}} by scanning the province bitmap.

    For each pair of horizontally- or vertically-adjacent pixels with different
    colors, the two province IDs they belong to are recorded as adjacent.
    Diagonals are deliberately ignored — HOI4 treats only orthogonal contact
    as a real border.
    """
    # Local imports so callers that don't need adjacency don't pay PIL/numpy
    # import cost. numpy in particular is heavy.
    from PIL import Image
    import numpy as np

    img = Image.open(provinces_bmp).convert("RGB")
    arr = np.array(img)
    packed = (
        (arr[:, :, 0].astype(np.uint32) << 16)
        | (arr[:, :, 1].astype(np.uint32) << 8)
        | arr[:, :, 2].astype(np.uint32)
    )
    packed_to_id = {
        (r << 16) | (g << 8) | b: pid for (r, g, b), pid in color_to_id.items()
    }

    adj: Dict[int, Set[int]] = {}

    def _record_pairs(a, b):
        mask = a != b
        # np.unique over stacked pairs collapses duplicate edges so we only
        # do the dict work O(unique edges) instead of O(pixels).
        pairs = np.unique(np.stack([a[mask], b[mask]], axis=1), axis=0)
        for x, y in pairs:
            ix = packed_to_id.get(int(x))
            iy = packed_to_id.get(int(y))
            if ix is None or iy is None or ix == iy:
                continue
            adj.setdefault(ix, set()).add(iy)
            adj.setdefault(iy, set()).add(ix)

    _record_pairs(packed[:, :-1], packed[:, 1:])  # horizontal
    _record_pairs(packed[:-1, :], packed[1:, :])  # vertical

    return adj


_STATE_ID_RE = re.compile(r"\bid\s*=\s*(\d+)")
_STATE_PROVS_RE = re.compile(r"provinces\s*=\s*\{([^}]*)\}", re.DOTALL)


def _read_state_file(path: Path) -> Optional[Tuple[int, Set[int]]]:
    """Parse one state file into (state_id, province_id_set), or None if it
    doesn't conform to the expected shape."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    mid = _STATE_ID_RE.search(text)
    mp = _STATE_PROVS_RE.search(text)
    if not mid or not mp:
        return None
    sid = int(mid.group(1))
    provs = {int(x) for x in mp.group(1).split() if x.isdigit()}
    return sid, provs


def parse_state_files(
    layered_sources: List[List[Path]],
) -> Tuple[Dict[int, Set[int]], Dict[int, int]]:
    """Parse layered state-file sources into (state_to_provinces, province_to_state).

    `layered_sources` comes from ``resolve_dir_files``: a list of file lists
    in load order, lowest priority first. We resolve in two passes:

    1. Per source, build {state_id: provinces}. If a source ships any file
       with state ID N, that source's claim for N wins for that layer
       (within-source duplicates use the last-seen file's claim, which is
       arbitrary but vanishingly rare in practice).
    2. Merge layers in order, with higher layers entirely **replacing** any
       lower layer's claim on the same state ID.

    The two-pass approach is the fix for HOI4's filename-vs-state-ID
    mismatch: KR can ship ``13-Estonia.txt`` redefining state 13, while
    base game's ``13-Karelia.txt`` (different filename) is not removed
    from disk but must be ignored.
    """
    final_state_to_provs: Dict[int, Set[int]] = {}
    for source_files in layered_sources:
        layer: Dict[int, Set[int]] = {}
        for path in source_files:
            parsed = _read_state_file(path)
            if parsed is None:
                continue
            sid, provs = parsed
            layer[sid] = provs
        # Higher layer wins outright for any state id it touches.
        final_state_to_provs.update(layer)

    prov_to_state: Dict[int, int] = {}
    for sid, provs in final_state_to_provs.items():
        for p in provs:
            prov_to_state[p] = sid
    return final_state_to_provs, prov_to_state


# ---------------------------------------------------------------------------
# Save parsing (state ownership)
# ---------------------------------------------------------------------------

def _walk_block(text: str, open_pos: int) -> int:
    """Return index one past the matching ``}`` for an already-consumed ``{``."""
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


_OWNER_RE = re.compile(r'\bowner\s*=\s*"?([A-Z0-9]{3})"?')


def parse_state_owners(save_text: str) -> Dict[int, str]:
    """Return {state_id: owner_tag} for every state in the save's states={}
    section. Skips states with no owner (rare but possible)."""
    section_match = re.search(r"\nstates=\{", save_text)
    if not section_match:
        return {}
    section_start = section_match.end()
    section_end = _walk_block(save_text, section_start)
    section = save_text[section_start:section_end - 1]

    owners: Dict[int, str] = {}
    for entry in re.finditer(r"\n\t(\d+)=\{", section):
        sid = int(entry.group(1))
        body_start = entry.end()
        body_end = _walk_block(section, body_start)
        body = section[body_start:body_end - 1]
        m = _OWNER_RE.search(body)
        if m:
            owners[sid] = m.group(1)
    return owners


# ---------------------------------------------------------------------------
# Composition: country -> land neighbors
# ---------------------------------------------------------------------------

def compute_neighbors(
    tag: str,
    state_owners: Dict[int, str],
    state_to_provs: Dict[int, Set[int]],
    prov_to_state: Dict[int, int],
    province_adjacency: Dict[int, Set[int]],
    sea_lake_provinces: Set[int],
) -> List[str]:
    """Return the sorted list of land-neighbor country tags for `tag`.

    Pure composition: given all four lookups, this is just set operations.
    Easy to unit-test without touching disk.
    """
    target_states = {s for s, o in state_owners.items() if o == tag}
    target_provs: Set[int] = set()
    for s in target_states:
        target_provs |= state_to_provs.get(s, set())

    neighbor_provs: Set[int] = set()
    for p in target_provs:
        for n in province_adjacency.get(p, ()):
            if n in sea_lake_provinces or n in target_provs:
                continue
            neighbor_provs.add(n)

    neighbor_states = {
        prov_to_state[p] for p in neighbor_provs if p in prov_to_state
    }
    neighbor_tags = {
        state_owners.get(s) for s in neighbor_states if state_owners.get(s)
    }
    neighbor_tags.discard(tag)  # never list self
    return sorted(neighbor_tags)


def get_country_neighbors(
    save_text: str,
    tag: str,
    hoi4_path: Optional[Path] = None,
    user_data_path: Optional[Path] = None,
) -> List[str]:
    """High-level entry point. Resolves the active playset, loads map data,
    extracts state ownership from the save, and returns the sorted list of
    land-neighbor country tags."""
    if hoi4_path is None:
        hoi4_path = Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV"
        )
    mod_roots = resolve_active_playset_mod_roots(user_data_path)

    def_csv = resolve_file("map/definition.csv", mod_roots, hoi4_path)
    bmp = resolve_file("map/provinces.bmp", mod_roots, hoi4_path)
    if def_csv is None or bmp is None:
        raise FileNotFoundError(
            "Could not resolve map/definition.csv or map/provinces.bmp"
        )

    color_to_id, sea_lake = parse_province_definitions(def_csv)
    adj = build_province_adjacency(bmp, color_to_id)

    state_files = resolve_dir_files("history/states", "*.txt", mod_roots, hoi4_path)
    state_to_provs, prov_to_state = parse_state_files(state_files)

    state_owners = parse_state_owners(save_text)

    return compute_neighbors(
        tag, state_owners, state_to_provs, prov_to_state, adj, sea_lake
    )


def compute_country_provinces(
    tag: str,
    state_owners: Dict[int, str],
    state_to_provs: Dict[int, Set[int]],
) -> Dict[int, Set[int]]:
    """Return ``{state_id: {province_ids}}`` for every state owned by `tag`.

    Pure composition: no I/O. Skips states the country owns but whose
    state file isn't in `state_to_provs` (e.g. a state in the save that
    no current mod defines — possible after a playset change).
    """
    return {
        sid: state_to_provs[sid]
        for sid, owner in state_owners.items()
        if owner == tag and sid in state_to_provs
    }


def get_country_provinces(
    save_text: str,
    tag: str,
    hoi4_path: Optional[Path] = None,
    user_data_path: Optional[Path] = None,
) -> Dict[int, Set[int]]:
    """High-level entry point. Returns ``{state_id: {province_ids}}`` for
    every state the given country owns.

    Cheaper than neighbors — no bitmap scan, no adjacency. We need only
    the mod-aware state files and the save's state-ownership table.
    """
    if hoi4_path is None:
        hoi4_path = Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV"
        )
    mod_roots = resolve_active_playset_mod_roots(user_data_path)

    state_files = resolve_dir_files("history/states", "*.txt", mod_roots, hoi4_path)
    state_to_provs, _ = parse_state_files(state_files)

    state_owners = parse_state_owners(save_text)
    return compute_country_provinces(tag, state_owners, state_to_provs)
