"""Tests for national-idea extraction & display.

Three layers:
- save_parsing.parse_country_ideas: pure save extraction.
- localization.get_idea_display: name + level-stripping fallback + hidden
  detection. The level-stripping case is the load-bearing one that
  prevented WRA_german_support_1 from rendering as "German Support 1".
- list_country_ideas.get_country_ideas: composition + hidden filter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import write_yml

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from list_country_ideas import get_country_ideas  # noqa: E402
from save_parsing import parse_country_ideas  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic save builder
# ---------------------------------------------------------------------------

def _make_country_block_with_ideas(
    tag: str,
    ideas: list[str],
    *,
    include_marker: bool = True,
) -> str:
    """Build a minimal country block with politics.ideas={...}. The
    politics block must sit at 2 tabs so ideas={ lands at 3."""
    marker = '\t\tfocus_tree="x"\n' if include_marker else ""
    return (
        f"\n\t{tag}=" + "{\n"
        f"{marker}"
        '\t\truling_party="paternal_autocrat"\n'
        "\t\tpolitics={\n"
        "\t\t\tideas={ " + " ".join(ideas) + " }\n"
        "\t\t}\n"
        "\t}\n"
    )


# ---------------------------------------------------------------------------
# parse_country_ideas
# ---------------------------------------------------------------------------

class TestParseCountryIdeas:
    def test_extracts_ids_in_order(self):
        save = "prefix" + _make_country_block_with_ideas(
            "WRA", ["civilian_economy", "export_focus", "volunteer_only"]
        )
        result = parse_country_ideas(save, "WRA")
        assert result == ["civilian_economy", "export_focus", "volunteer_only"]

    def test_empty_ideas_block(self):
        save = "prefix\n\tWRA={\n" \
               '\t\truling_party="x"\n' \
               "\t\tpolitics={\n" \
               "\t\t\tideas={ }\n" \
               "\t\t}\n" \
               "\t}\n"
        assert parse_country_ideas(save, "WRA") == []

    def test_returns_none_when_country_missing(self):
        save = "prefix" + _make_country_block_with_ideas("GER", ["x"])
        assert parse_country_ideas(save, "WRA") is None

    def test_ignores_equipment_variant_ideas_blocks(self):
        # Equipment variants use ideas={ ... } at a different indentation.
        # Our regex requires \n\t\t\tideas={ so it only matches the politics
        # block. This test guards against regressions if someone loosens it.
        equipment_block = (
            "convoy_1={\n"
            "\tid={ id=1 type=70 }\n"
            "\tcan_upgrade_variant=yes\n"
            "\tideas={ HAW_some_admiral_eco_ade }\n"
            "}\n"
        )
        save = equipment_block + _make_country_block_with_ideas(
            "WRA", ["civilian_economy"]
        )
        result = parse_country_ideas(save, "WRA")
        # Must NOT include the equipment ideas — only the politics ones.
        assert result == ["civilian_economy"]


# ---------------------------------------------------------------------------
# Localizer get_idea_display
# ---------------------------------------------------------------------------

class TestGetIdeaDisplay:
    def test_basic_name_and_description(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "civilian_economy": "Civilian Economy",
                "civilian_economy_desc": "Civilian production focus.",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        d = loc.get_idea_display("civilian_economy")
        assert d["name"] == "Civilian Economy"
        assert d["description"] == "Civilian production focus."
        assert d["is_hidden"] is False

    def test_strips_color_codes_for_name_clean(self, make_localizer, hoi4_install):
        # KR uses §R / §! / §Y in some idea names for severity coloring.
        # name preserves raw; name_clean strips it for single-line display.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {"_RAW:1": ' RUS_resistance:0 "Socialist Resistance: §RStrong§!"'},
        )
        loc = make_localizer()
        loc.load_all_files()
        d = loc.get_idea_display("RUS_resistance")
        assert "§R" in d["name"]
        assert d["name_clean"] == "Socialist Resistance: Strong"

    def test_level_stripping_fallback(self, make_localizer, hoi4_install):
        # The WRA_german_support_1 -> WRA_german_support case: the save has
        # the levelled ID but locale only has the base. We must resolve.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "WRA_german_support": "German Backing",
                "WRA_german_support_desc": "Backed by Germany.",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        d = loc.get_idea_display("WRA_german_support_1")
        assert d["name"] == "German Backing"
        assert d["description"] == "Backed by Germany."
        assert d["is_hidden"] is False

    def test_exact_key_beats_level_stripped(self, make_localizer, hoi4_install):
        # When a level-specific locale exists, it should be preferred over
        # the base name. Some KR ideas have per-level text.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "RUS_resistance": "Resistance",
                "RUS_resistance_1": "Resistance: Mild",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.get_idea_display("RUS_resistance_1")["name"] == "Resistance: Mild"

    def test_hidden_suffix_marks_idea_hidden(self, make_localizer):
        # Even if a _hidden idea had a locale entry, the suffix is the
        # authoritative signal — these are UI-hidden by convention.
        loc = make_localizer()
        d = loc.get_idea_display("PNSD_hidden")
        assert d["is_hidden"] is True
        assert d["name"] == ""

    def test_no_locale_at_all_marks_idea_hidden(self, make_localizer):
        # Scripted-internal ideas often have no locale at all. These get
        # flagged as hidden so the default CLI output skips them rather
        # than showing a cleaned-key like "Rcw Major Wra".
        loc = make_localizer()
        d = loc.get_idea_display("RCW_major_WRA")
        assert d["is_hidden"] is True
        assert d["name"] == ""


# ---------------------------------------------------------------------------
# Composition: get_country_ideas
# ---------------------------------------------------------------------------

class TestGetCountryIdeas:
    def _make_loc(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "civilian_economy": "Civilian Economy",
                "WRA_german_support": "German Backing",
                "WRA_low_legitimacy": "Low Legitimacy",
                "WRA_low_legitimacy_desc": "Government has weak legitimacy.",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        return loc

    def test_filters_hidden_by_default(self, make_localizer, hoi4_install):
        loc = self._make_loc(make_localizer, hoi4_install)
        save = "x" + _make_country_block_with_ideas("WRA", [
            "civilian_economy", "PNSD_hidden", "RCW_major_WRA", "WRA_low_legitimacy"
        ])
        result = get_country_ideas(save, "WRA", loc)
        ids = [r["id"] for r in result]
        # Both hidden-by-suffix and hidden-by-no-locale are filtered.
        assert ids == ["civilian_economy", "WRA_low_legitimacy"]

    def test_include_hidden_returns_everything(self, make_localizer, hoi4_install):
        loc = self._make_loc(make_localizer, hoi4_install)
        save = "x" + _make_country_block_with_ideas("WRA", [
            "civilian_economy", "PNSD_hidden", "RCW_major_WRA"
        ])
        result = get_country_ideas(save, "WRA", loc, include_hidden=True)
        ids = [r["id"] for r in result]
        assert ids == ["civilian_economy", "PNSD_hidden", "RCW_major_WRA"]
        # Hidden entries still carry the is_hidden flag so consumers can
        # filter or style them differently.
        hidden_flags = {r["id"]: r["is_hidden"] for r in result}
        assert hidden_flags == {
            "civilian_economy": False,
            "PNSD_hidden": True,
            "RCW_major_WRA": True,
        }

    def test_preserves_save_order(self, make_localizer, hoi4_install):
        loc = self._make_loc(make_localizer, hoi4_install)
        save = "x" + _make_country_block_with_ideas("WRA", [
            "WRA_low_legitimacy", "civilian_economy", "WRA_german_support"
        ])
        result = get_country_ideas(save, "WRA", loc)
        assert [r["id"] for r in result] == [
            "WRA_low_legitimacy", "civilian_economy", "WRA_german_support"
        ]

    def test_description_resolved(self, make_localizer, hoi4_install):
        loc = self._make_loc(make_localizer, hoi4_install)
        save = "x" + _make_country_block_with_ideas("WRA", ["WRA_low_legitimacy"])
        result = get_country_ideas(save, "WRA", loc)
        assert result[0]["description"] == "Government has weak legitimacy."

    def test_returns_none_when_country_missing(self, make_localizer):
        loc = make_localizer()
        save = "x" + _make_country_block_with_ideas("GER", ["civilian_economy"])
        assert get_country_ideas(save, "WRA", loc) is None
