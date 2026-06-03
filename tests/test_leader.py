"""Tests for the thin leader-composer wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import write_yml

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from list_country_leader import get_country_leader  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic save builder — minimal politics block with parties + a
# character_manager entry so the leader name resolves.
# ---------------------------------------------------------------------------

def _make_country_block(tag: str, ruling: str, parties: list[dict]) -> str:
    party_blocks = []
    for p in parties:
        leaders_block = ""
        for L in p.get("leaders", []):
            leaders_block += (
                "{\n"
                f'\t\t\t\t\t\tideology="{L["ideology"]}"\n'
                f'\t\t\t\t\t\tcharacter={{ id={L["id"]} type=73 }}\n'
                "\t\t\t\t\t}\n"
            )
        party_blocks.append(
            f"\n\t\t\t\t{p['id']}=" + "{\n"
            f"\t\t\t\t\tpopularity={p['popularity']}\n"
            "\t\t\t\t\tcountry_leader={\n"
            f"{leaders_block}"
            "\t\t\t\t\t}\n"
            "\t\t\t\t}"
        )
    return (
        f"\n\t{tag}=" + "{\n"
        '\t\tfocus_tree="x"\n'
        f'\t\truling_party="{ruling}"\n'
        '\t\tcosmetic_tag=""\n'
        "\t\tpolitics={\n"
        "\t\t\tparties={"
        + "".join(party_blocks) + "\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
    )


def _character_entry(char_id: int, name: str) -> str:
    return (
        "\tcharacter={\n"
        f"\t\tid={{ id={char_id} type=73 }}\n"
        f'\t\ttoken="X"\n'
        f'\t\tname="{name}"\n'
        '\t\tcountry="X"\n'
        "\t}\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetCountryLeader:
    def _make_loc(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "WRA_paternal_autocrat_party": "SZR",
                "WRA_paternal_autocrat_party_long": "Sovet Zapadnoy Rossii",
                "WRA_social_democrat_party": "RSDRP",
                "WRA_social_democrat_party_long": "Sotsial-Demokraty",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        return loc

    def test_returns_ruling_party_and_leader(self, make_localizer, hoi4_install):
        loc = self._make_loc(make_localizer, hoi4_install)
        save = (
            "prefix\n"
            + _character_entry(5511, "Pavel Bermondt-Avalov")
            + _make_country_block("WRA", ruling="paternal_autocrat", parties=[
                {"id": "paternal_autocrat", "popularity": 33.98,
                 "leaders": [{"ideology": "junta_subtype", "id": 5511}]},
                {"id": "social_democrat", "popularity": 12.0, "leaders": []},
            ])
        )
        result = get_country_leader(save, "WRA", loc)
        assert result is not None
        assert result["tag"] == "WRA"
        assert result["ruling_party_id"] == "paternal_autocrat"
        assert result["ruling_party_short"] == "SZR"
        assert result["ruling_party_long"] == "Sovet Zapadnoy Rossii"
        assert result["leader_id"] == 5511
        assert result["leader_name"] == "Pavel Bermondt-Avalov"
        assert result["leader_ideology"] == "junta_subtype"

    def test_returns_none_for_missing_country(self, make_localizer):
        loc = make_localizer()
        save = "prefix" + _make_country_block("GER", ruling="paternal_autocrat", parties=[
            {"id": "paternal_autocrat", "popularity": 50, "leaders": []},
        ])
        assert get_country_leader(save, "WRA", loc) is None

    def test_handles_party_with_no_leaders(self, make_localizer, hoi4_install):
        # The save shape allows a party to have an empty country_leader={}
        # array. We must produce a result with None leader fields, not crash
        # and not skip the country entirely.
        loc = self._make_loc(make_localizer, hoi4_install)
        save = "prefix" + _make_country_block("WRA", ruling="paternal_autocrat", parties=[
            {"id": "paternal_autocrat", "popularity": 50, "leaders": []},
        ])
        result = get_country_leader(save, "WRA", loc)
        assert result is not None
        assert result["leader_id"] is None
        assert result["leader_name"] is None
        assert result["leader_ideology"] is None

    def test_falls_back_to_most_popular_when_ruling_party_id_missing(
        self, make_localizer, hoi4_install
    ):
        # If the ruling_party field in the save points at an id that isn't
        # in the parties table (rare — possible mid-event state), fall back
        # to the most popular party rather than returning None. Better to
        # show a consumer SOMETHING reasonable than nothing.
        loc = self._make_loc(make_localizer, hoi4_install)
        save = (
            "prefix\n"
            + _character_entry(999, "Some Leader")
            + _make_country_block("WRA", ruling="totalist", parties=[
                {"id": "paternal_autocrat", "popularity": 50,
                 "leaders": [{"ideology": "x_subtype", "id": 999}]},
                {"id": "social_democrat", "popularity": 12, "leaders": []},
            ])
        )
        result = get_country_leader(save, "WRA", loc)
        assert result is not None
        # ruling_party from hints was "totalist" (not in parties);
        # fallback picked paternal_autocrat (highest popularity).
        assert result["ruling_party_id"] == "paternal_autocrat"
        assert result["leader_name"] == "Some Leader"

    def test_accepts_precomputed_hints_and_characters(
        self, make_localizer, hoi4_install
    ):
        # Callers iterating over every country in a save can pass in a
        # single full-save parse to avoid repeating it 400 times.
        loc = self._make_loc(make_localizer, hoi4_install)
        save = (
            "prefix\n"
            + _character_entry(5511, "Pavel Bermondt-Avalov")
            + _make_country_block("WRA", ruling="paternal_autocrat", parties=[
                {"id": "paternal_autocrat", "popularity": 50,
                 "leaders": [{"ideology": "x_subtype", "id": 5511}]},
            ])
        )

        # Pre-compute and pass in. Tampered values should be respected
        # over re-parsing — that's the contract.
        hints = {"WRA": {"cosmetic_tag": None, "ruling_party": "paternal_autocrat"}}
        chars = {5511: "Tampered Name"}
        result = get_country_leader(save, "WRA", loc, characters=chars, hints=hints)
        assert result["leader_name"] == "Tampered Name"
