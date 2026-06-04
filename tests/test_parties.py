"""Tests for political-party extraction.

Covers three layers:
- save_parsing.parse_country_parties: pure save-text parse.
- save_parsing.parse_character_names: with the type=73 restriction that
  prevented equipment/organisation IDs from leaking through as character
  names (the 'artillery_garanganze_ktg' bug found while building this).
- localization.get_party_names: short / long_raw / long_clean shapes.
- list_country_parties.get_country_parties: composition layer with
  name-override handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import write_yml

# scripts/ isn't on the python path by default; add it for the import below.
_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from list_country_parties import get_country_parties  # noqa: E402
from save_parsing import (  # noqa: E402
    parse_character_names,
    parse_country_parties,
)


# ---------------------------------------------------------------------------
# Synthetic save fragments
# ---------------------------------------------------------------------------

def _make_country_block(
    tag: str,
    parties: list[dict],
    *,
    ruling_party: str = "paternal_autocrat",
    include_marker: bool = True,
) -> str:
    """Build a country block with a politics.parties section."""
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
        name_line = (
            f'\t\t\t\t\tname="{p["name_override"]}"\n'
            if p.get("name_override") else ""
        )
        long_line = (
            f'\t\t\t\t\tlong_name="{p["long_name_override"]}"\n'
            if p.get("long_name_override") else ""
        )
        default_line = (
            f'\t\t\t\t\tdefault={"yes" if p.get("default") else "no"}\n'
            if "default" in p else ""
        )
        party_blocks.append(
            f"\n\t\t\t\t{p['id']}=" + "{\n"
            f"{default_line}"
            f"{name_line}"
            f"{long_line}"
            f"\t\t\t\t\tpopularity={p['popularity']}\n"
            f"\t\t\t\t\tcountry_leader=" + "{\n"
            f"{leaders_block}"
            "\t\t\t\t\t}\n"
            "\t\t\t\t}"
        )
    marker = '\t\tfocus_tree="x"\n' if include_marker else ""
    return (
        f"\n\t{tag}=" + "{\n"
        f"{marker}"
        f'\t\truling_party="{ruling_party}"\n'
        "\t\tpolitics={\n"
        "\t\t\tparties={"
        + "".join(party_blocks) + "\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
    )


def _make_character_entry(char_id: int, name: str, *, type_code: int = 73) -> str:
    """Build a character-manager character entry."""
    return (
        "\t\tcharacter={\n"
        f"\t\t\tid={{ id={char_id} type={type_code} }}\n"
        f'\t\t\ttoken="X_someone"\n'
        f'\t\t\tname="{name}"\n'
        '\t\t\tcountry="X"\n'
        "\t\t}\n"
    )


# ---------------------------------------------------------------------------
# parse_country_parties
# ---------------------------------------------------------------------------

class TestParseCountryParties:
    def test_extracts_popularity_and_default(self):
        save = "x" + _make_country_block("CAN", [
            {"id": "paternal_autocrat", "popularity": 33.5, "default": True, "leaders": []},
            {"id": "social_democrat",  "popularity": 12.0, "default": False, "leaders": []},
        ])
        parties = parse_country_parties(save, "CAN")
        assert parties is not None
        assert parties["paternal_autocrat"]["popularity"] == 33.5
        assert parties["paternal_autocrat"]["is_default"] is True
        assert parties["social_democrat"]["is_default"] is False

    def test_zero_popularity_present(self):
        # `popularity=0` is the common "exists but has no support" case.
        save = "x" + _make_country_block("CAN", [
            {"id": "totalist", "popularity": 0, "leaders": []},
        ])
        parties = parse_country_parties(save, "CAN")
        assert parties["totalist"]["popularity"] == 0.0

    def test_extracts_name_overrides(self):
        # KR uses this to make a party display as someone else's
        # (e.g. CAN's social_liberal shown as GBR's Liberal Party).
        save = "x" + _make_country_block("CAN", [
            {
                "id": "social_liberal",
                "popularity": 5.0,
                "name_override": "GBR_social_liberal_party",
                "long_name_override": "GBR_social_liberal_party_long",
                "leaders": [],
            },
        ])
        parties = parse_country_parties(save, "CAN")
        assert parties["social_liberal"]["name_override"] == "GBR_social_liberal_party"
        assert parties["social_liberal"]["long_name_override"] == "GBR_social_liberal_party_long"

    def test_extracts_leaders(self):
        save = "x" + _make_country_block("WRA", [
            {
                "id": "paternal_autocrat",
                "popularity": 33.98,
                "leaders": [
                    {"ideology": "junta_subtype", "id": 5511},
                ],
            },
        ])
        parties = parse_country_parties(save, "WRA")
        leaders = parties["paternal_autocrat"]["leaders"]
        assert leaders == [{"ideology": "junta_subtype", "character_id": 5511}]

    def test_extracts_multiple_leaders_per_party(self):
        # CAN's social_liberal sometimes has multiple leaders for different
        # sub-ideologies. The array must come through intact.
        save = "x" + _make_country_block("CAN", [
            {
                "id": "social_liberal",
                "popularity": 0,
                "leaders": [
                    {"ideology": "classical_liberalism_subtype", "id": 72368},
                    {"ideology": "classical_liberalism_subtype", "id": 528},
                ],
            },
        ])
        parties = parse_country_parties(save, "CAN")
        leader_ids = [L["character_id"] for L in parties["social_liberal"]["leaders"]]
        assert leader_ids == [72368, 528]

    def test_returns_none_when_country_missing(self):
        save = "x" + _make_country_block("CAN", [
            {"id": "paternal_autocrat", "popularity": 50, "leaders": []},
        ])
        assert parse_country_parties(save, "GER") is None

    def test_returns_none_when_no_parties_block(self):
        # Country block exists but no politics.parties subsection.
        save = (
            "x\n\tCAN={\n"
            "\t\truling_party=\"foo\"\n"
            "\t\tstability=0.5\n"
            "\t}\n"
        )
        assert parse_country_parties(save, "CAN") is None


# ---------------------------------------------------------------------------
# parse_character_names — the type=73 restriction
# ---------------------------------------------------------------------------

class TestParseCharacterNames:
    def test_extracts_named_character(self):
        save = "prefix\n" + _make_character_entry(70894, "Ilya Polyakov")
        assert parse_character_names(save) == {70894: "Ilya Polyakov"}

    def test_ignores_non_character_id_entries(self):
        # type=70 = equipment, type=79 = organisation. These reuse the same
        # numeric IDs as characters and have their OWN `name=` field. They
        # must NOT be picked up — that was the 'artillery_garanganze_ktg'
        # bug we hit during development.
        save = (
            "equipment_block={\n"
            "\tid={ id=5511 type=70 }\n"
            '\tcreator="BRY"\n'
            "}\n"
            "organisation_block={\n"
            "\tid={ id=5511 type=79 }\n"
            '\tname="artillery_garanganze_ktg"\n'
            "}\n"
            + _make_character_entry(5511, "Pavel Bermondt-Avalov")
        )
        result = parse_character_names(save)
        assert result == {5511: "Pavel Bermondt-Avalov"}

    def test_returns_empty_dict_when_no_characters(self):
        assert parse_character_names("nothing here") == {}


# ---------------------------------------------------------------------------
# localizer get_party_names
# ---------------------------------------------------------------------------

class TestGetPartyNames:
    def test_returns_short_long_raw_and_clean(self, make_localizer, hoi4_install):
        # Use the literal-line escape so we can store the §L/\n KR convention.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "WRA_paternal_autocrat_party": "SZR",
                "_RAW:1": (
                    ' WRA_paternal_autocrat_party_long:0 '
                    '"Sovet Zapadnoy Rossii\\n§LCouncil of Western Russia§!"'
                ),
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        names = loc.get_party_names("WRA", "paternal_autocrat")
        assert names["short"] == "SZR"
        # raw preserves the formatting.
        assert "§L" in names["long_raw"]
        # clean truncates at the first \n and strips §X codes.
        assert names["long_clean"] == "Sovet Zapadnoy Rossii"
        # long_full keeps both lines (translation included) and strips color
        # codes — this is what HOI4 renders in the in-game party tooltip.
        assert names["long_full"] == (
            "Sovet Zapadnoy Rossii\nCouncil of Western Russia"
        )

    def test_missing_keys_become_empty_strings(self, make_localizer):
        # The localizer's get_localized_text would otherwise return a
        # cleaned-key like "Unknown Party" — get_party_names must suppress
        # that so the CLI can show "" cleanly.
        loc = make_localizer()
        names = loc.get_party_names("ZZZ", "totalist")
        assert names == {
            "short": "", "long_raw": "", "long_clean": "", "long_full": "",
        }


# ---------------------------------------------------------------------------
# get_country_parties composition
# ---------------------------------------------------------------------------

class TestGetCountryParties:
    def test_full_composition(self, make_localizer, hoi4_install):
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

        save = (
            "prefix\n"
            + _make_character_entry(5511, "Pavel Bermondt-Avalov")
            + _make_country_block("WRA", [
                {
                    "id": "paternal_autocrat",
                    "popularity": 33.98,
                    "default": True,
                    "leaders": [{"ideology": "junta_subtype", "id": 5511}],
                },
                {
                    "id": "social_democrat",
                    "popularity": 12.5,
                    "leaders": [],
                },
            ], ruling_party="paternal_autocrat")
        )

        result = get_country_parties(save, "WRA", loc)
        assert result is not None
        # Sorted by popularity desc.
        assert [p["id"] for p in result] == ["paternal_autocrat", "social_democrat"]
        # First party: full info including resolved leader name.
        first = result[0]
        assert first["popularity"] == 33.98
        assert first["is_ruling"] is True
        assert first["short"] == "SZR"
        assert first["long_clean"] == "Sovet Zapadnoy Rossii"
        assert first["leaders"] == [{
            "ideology": "junta_subtype",
            "character_id": 5511,
            "name": "Pavel Bermondt-Avalov",
        }]
        # Second party: no leaders, not ruling.
        assert result[1]["is_ruling"] is False
        assert result[1]["leaders"] == []

    def test_name_override_uses_override_key(self, make_localizer, hoi4_install):
        # CAN's social_liberal points at GBR_social_liberal_party_long.
        # The composition layer must use the override key, not the
        # canonical CAN_social_liberal_party_long key.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "CAN_social_liberal_party": "Canadian Liberals",
                "CAN_social_liberal_party_long": "Canadian Liberal Party",
                "GBR_social_liberal_party": "Progressive Liberals",
                "GBR_social_liberal_party_long": "Liberal Party (Progressives)",
            },
        )
        loc = make_localizer()
        loc.load_all_files()

        save = "x" + _make_country_block("CAN", [
            {
                "id": "social_liberal",
                "popularity": 0,
                "name_override": "GBR_social_liberal_party",
                "long_name_override": "GBR_social_liberal_party_long",
                "leaders": [],
            },
        ])
        result = get_country_parties(save, "CAN", loc)
        assert result is not None
        assert result[0]["short"] == "Progressive Liberals"
        assert result[0]["long_clean"] == "Liberal Party (Progressives)"

    def test_unknown_character_id_keeps_none_name(self, make_localizer):
        loc = make_localizer()
        save = "x" + _make_country_block("WRA", [
            {
                "id": "paternal_autocrat",
                "popularity": 50,
                "leaders": [{"ideology": "x", "id": 99999}],
            },
        ])
        result = get_country_parties(save, "WRA", loc, characters={})
        # Character lookup failed but the structure is preserved with None.
        assert result[0]["leaders"][0]["name"] is None
        assert result[0]["leaders"][0]["character_id"] == 99999
