"""Tests for src/map_data.py.

The expensive bitmap-scan path is exercised with a tiny synthetic 4x4 image so
tests stay fast; the parser / resolver / composition layers are exercised with
synthetic state files and SQLite DBs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import build_launcher_db

from map_data import (
    build_province_adjacency,
    compute_neighbors,
    parse_province_definitions,
    parse_state_files,
    parse_state_owners,
    resolve_active_playset_mod_roots,
    resolve_dir_files,
    resolve_file,
)


# ---------------------------------------------------------------------------
# Playset / mod-root resolution
# ---------------------------------------------------------------------------

class TestResolveActivePlaysetModRoots:
    def test_empty_when_db_missing(self, user_dir):
        assert resolve_active_playset_mod_roots(user_dir) == []

    def test_returns_enabled_mods_in_position_order(self, user_dir):
        roots = [user_dir / "mods" / name for name in ("A", "B", "C")]
        for r in roots:
            r.mkdir(parents=True)
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="PS",
            mods=[
                {"display_name": "B", "dir_path": roots[1], "enabled": True, "position": 2},
                {"display_name": "C", "dir_path": roots[2], "enabled": False, "position": 3},
                {"display_name": "A", "dir_path": roots[0], "enabled": True, "position": 1},
            ],
        )
        result = resolve_active_playset_mod_roots(user_dir)
        # C is disabled and must be excluded; A and B in position order.
        assert result == [roots[0], roots[1]]


# ---------------------------------------------------------------------------
# File resolution (per-filename and per-directory)
# ---------------------------------------------------------------------------

class TestResolveFile:
    def test_returns_none_when_nothing_ships_file(self, hoi4_install):
        assert resolve_file("map/missing.csv", [], hoi4_install) is None

    def test_falls_back_to_base_game(self, hoi4_install):
        base = hoi4_install / "map" / "definition.csv"
        base.parent.mkdir(parents=True)
        base.write_text("base content")
        assert resolve_file("map/definition.csv", [], hoi4_install) == base

    def test_mod_overrides_base_game(self, tmp_path, hoi4_install):
        base = hoi4_install / "map" / "definition.csv"
        base.parent.mkdir(parents=True)
        base.write_text("base")
        mod = tmp_path / "mod" / "map" / "definition.csv"
        mod.parent.mkdir(parents=True)
        mod.write_text("mod")
        winner = resolve_file("map/definition.csv", [tmp_path / "mod"], hoi4_install)
        assert winner == mod

    def test_later_mod_overrides_earlier_mod(self, tmp_path, hoi4_install):
        early = tmp_path / "early" / "map" / "definition.csv"
        late = tmp_path / "late" / "map" / "definition.csv"
        for f in (early, late):
            f.parent.mkdir(parents=True)
            f.write_text("x")
        result = resolve_file(
            "map/definition.csv",
            [tmp_path / "early", tmp_path / "late"],
            hoi4_install,
        )
        assert result == late


class TestResolveDirFiles:
    def test_returns_layered_sources_in_load_order(self, tmp_path, hoi4_install):
        # Base ships 1-Foo.txt and 2-Bar.txt.
        for name in ("1-Foo.txt", "2-Bar.txt"):
            (hoi4_install / "history" / "states" / name).parent.mkdir(parents=True, exist_ok=True)
            (hoi4_install / "history" / "states" / name).write_text("x")
        # Mod ships 1-Foo.txt (replacing same filename) and 99-Mod.txt (new).
        mod_dir = tmp_path / "mod" / "history" / "states"
        mod_dir.mkdir(parents=True)
        (mod_dir / "1-Foo.txt").write_text("mod")
        (mod_dir / "99-Mod.txt").write_text("mod99")

        layers = resolve_dir_files(
            "history/states", "*.txt", [tmp_path / "mod"], hoi4_install
        )
        # First list = base, second = mod.
        assert len(layers) == 2
        assert {p.name for p in layers[0]} == {"1-Foo.txt", "2-Bar.txt"}
        assert {p.name for p in layers[1]} == {"1-Foo.txt", "99-Mod.txt"}


# ---------------------------------------------------------------------------
# province definitions
# ---------------------------------------------------------------------------

class TestParseProvinceDefinitions:
    def test_parses_id_color_and_classifies_sea(self, tmp_path):
        csv = tmp_path / "definition.csv"
        csv.write_text(
            "header_skipped\n"
            "1;0;0;0;land;false;plains;1\n"
            "2;255;0;0;sea;false;ocean;0\n"
            "3;0;255;0;lake;false;lakes;0\n"
            "4;0;0;255;land;true;plains;2\n",
            encoding="latin-1",
        )
        color_to_id, sea = parse_province_definitions(csv)
        assert color_to_id == {
            (0, 0, 0): 1,
            (255, 0, 0): 2,
            (0, 255, 0): 3,
            (0, 0, 255): 4,
        }
        assert sea == {2, 3}


# ---------------------------------------------------------------------------
# state-file parsing — the bug we just fixed
# ---------------------------------------------------------------------------

def _write_state(path: Path, sid: int, provinces: list[int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    prov_str = " ".join(str(p) for p in provinces)
    path.write_text(
        f"state = {{\n"
        f"\tid = {sid}\n"
        f"\tname = \"STATE_{sid}\"\n"
        f"\tprovinces = {{ {prov_str} }}\n"
        f"}}\n",
        encoding="utf-8",
    )


class TestParseStateFiles:
    def test_single_layer_builds_both_directions(self, tmp_path):
        _write_state(tmp_path / "1-A.txt", 1, [10, 11])
        _write_state(tmp_path / "2-B.txt", 2, [20])
        s_to_p, p_to_s = parse_state_files([sorted(tmp_path.glob("*.txt"))])
        assert s_to_p == {1: {10, 11}, 2: {20}}
        assert p_to_s == {10: 1, 11: 1, 20: 2}

    def test_mod_redefines_state_with_different_filename(self, tmp_path):
        # The KR-Estonia scenario: base game state 13 claims provinces
        # 100,101 in "13-Karelia.txt"; KR's "13-Estonia.txt" reassigns
        # state 13 to provinces 200,201. Province 100 must NOT remain
        # mapped to state 13 after merging.
        base = tmp_path / "base"
        mod = tmp_path / "mod"
        _write_state(base / "13-Karelia.txt", 13, [100, 101])
        _write_state(mod / "13-Estonia.txt", 13, [200, 201])

        s_to_p, p_to_s = parse_state_files(
            [sorted(base.glob("*.txt")), sorted(mod.glob("*.txt"))]
        )
        # State 13 now means Estonia, not Karelia.
        assert s_to_p == {13: {200, 201}}
        # And the old Karelia provinces don't still point at state 13.
        assert p_to_s == {200: 13, 201: 13}
        assert 100 not in p_to_s
        assert 101 not in p_to_s

    def test_orphan_base_state_file_does_not_leak_when_id_redefined(self, tmp_path):
        # The actual WRA bug: base game ships 813-Rakvere.txt (Estonia region,
        # province 4640). KR ships 813-SouthZambezia.txt (Africa, completely
        # different provinces) AND 13-Estonia.txt (which now claims 4640).
        # Province 4640 must map to state 13, not state 813.
        base = tmp_path / "base"
        mod = tmp_path / "mod"
        _write_state(base / "813-Rakvere.txt", 813, [4640])
        _write_state(mod / "813-SouthZambezia.txt", 813, [9000, 9001])
        _write_state(mod / "13-Estonia.txt", 13, [4640])

        s_to_p, p_to_s = parse_state_files(
            [sorted(base.glob("*.txt")), sorted(mod.glob("*.txt"))]
        )
        assert s_to_p[813] == {9000, 9001}
        assert s_to_p[13] == {4640}
        assert p_to_s[4640] == 13  # Estonia, not Zambezia.

    def test_skips_malformed_files(self, tmp_path):
        good = tmp_path / "1-Good.txt"
        bad = tmp_path / "2-Bad.txt"
        _write_state(good, 1, [10])
        bad.write_text("not a state file at all", encoding="utf-8")
        s_to_p, p_to_s = parse_state_files([sorted(tmp_path.glob("*.txt"))])
        assert s_to_p == {1: {10}}


# ---------------------------------------------------------------------------
# save state-ownership parsing
# ---------------------------------------------------------------------------

class TestParseStateOwners:
    def _make_save(self, *state_entries: tuple[int, str | None]) -> str:
        body = ""
        for sid, owner in state_entries:
            owner_line = f'\t\towner="{owner}"\n' if owner else ""
            body += (
                f"\n\t{sid}=" + "{\n"
                f"{owner_line}"
                "\t\tprovinces={ 1 2 3 }\n"
                "\t}\n"
            )
        return f"prefix\nstates=" + "{" + body + "}\nsuffix"

    def test_extracts_owners(self):
        save = self._make_save((10, "GER"), (11, "SOV"), (12, "USA"))
        assert parse_state_owners(save) == {10: "GER", 11: "SOV", 12: "USA"}

    def test_skips_states_without_owner(self):
        save = self._make_save((10, "GER"), (11, None))
        assert parse_state_owners(save) == {10: "GER"}

    def test_returns_empty_when_no_states_section(self):
        assert parse_state_owners("no states here") == {}


# ---------------------------------------------------------------------------
# compute_neighbors — pure composition
# ---------------------------------------------------------------------------

class TestComputeNeighbors:
    def test_basic_case(self):
        # A owns state 1 (province 10), B owns state 2 (province 20).
        # Provinces 10 and 20 are adjacent. A and B border each other.
        result = compute_neighbors(
            tag="A",
            state_owners={1: "A", 2: "B"},
            state_to_provs={1: {10}, 2: {20}},
            prov_to_state={10: 1, 20: 2},
            province_adjacency={10: {20}, 20: {10}},
            sea_lake_provinces=set(),
        )
        assert result == ["B"]

    def test_skips_sea_neighbors(self):
        # Province 99 is sea and must not surface a country.
        result = compute_neighbors(
            tag="A",
            state_owners={1: "A", 2: "B"},
            state_to_provs={1: {10}, 2: {20}},
            prov_to_state={10: 1, 20: 2},
            # 10 borders 99 (sea) which borders 20 (B). But sea is impassable
            # for land neighbors, so A does NOT neighbor B via sea.
            province_adjacency={10: {99}, 99: {10, 20}, 20: {99}},
            sea_lake_provinces={99},
        )
        assert result == []

    def test_excludes_self(self):
        result = compute_neighbors(
            tag="A",
            state_owners={1: "A", 2: "A"},
            state_to_provs={1: {10}, 2: {20}},
            prov_to_state={10: 1, 20: 2},
            province_adjacency={10: {20}, 20: {10}},
            sea_lake_provinces=set(),
        )
        assert result == []  # both states are A; no foreign neighbors.

    def test_returns_sorted(self):
        result = compute_neighbors(
            tag="A",
            state_owners={1: "A", 2: "Z", 3: "B", 4: "M"},
            state_to_provs={1: {10}, 2: {20}, 3: {30}, 4: {40}},
            prov_to_state={10: 1, 20: 2, 30: 3, 40: 4},
            province_adjacency={10: {20, 30, 40}, 20: {10}, 30: {10}, 40: {10}},
            sea_lake_provinces=set(),
        )
        assert result == ["B", "M", "Z"]


# ---------------------------------------------------------------------------
# Bitmap adjacency — tiny synthetic image so it stays fast.
# ---------------------------------------------------------------------------

class TestBuildProvinceAdjacency:
    def test_horizontal_and_vertical_edges_only(self, tmp_path):
        pytest.importorskip("PIL")
        pytest.importorskip("numpy")
        from PIL import Image
        # 3x3 image, three colors arranged like:
        #   A A B
        #   A A B
        #   C C C
        # A-B border on the right, A-C and B-C borders on the bottom.
        # Diagonal A-C/B-C contacts at corners are NOT borders.
        A = (255, 0, 0)
        B = (0, 255, 0)
        C = (0, 0, 255)
        pixels = [
            [A, A, B],
            [A, A, B],
            [C, C, C],
        ]
        img = Image.new("RGB", (3, 3))
        for y, row in enumerate(pixels):
            for x, col in enumerate(row):
                img.putpixel((x, y), col)
        bmp = tmp_path / "provinces.bmp"
        img.save(bmp)

        color_to_id = {A: 1, B: 2, C: 3}
        adj = build_province_adjacency(bmp, color_to_id)
        assert adj[1] == {2, 3}
        assert adj[2] == {1, 3}
        assert adj[3] == {1, 2}
