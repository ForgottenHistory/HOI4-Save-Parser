"""Tests for src/localization.py.

These exercise the behaviours that quietly break if someone refactors the
loader: parse patterns, override order, last-writer-wins across same-named
files, and playset/DB handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import build_launcher_db, write_yml


# ----------------------------------------------------------------------------
# YML parsing
# ----------------------------------------------------------------------------

class TestYmlParsing:
    def test_parses_versioned_keys(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "countries_l_english.yml",
            {"GER": "Germany", "SOV": "Soviet Union"},
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.translations["GER"] == "Germany"
        assert loc.translations["SOV"] == "Soviet Union"

    def test_parses_unversioned_keys(self, make_localizer, hoi4_install):
        # Event titles look like `EVENT.t: "Title"` — no version number.
        write_yml(
            hoi4_install / "localisation" / "english" / "events_l_english.yml",
            {"_RAW:1": ' AUS_political_events.16.t: "Nazis in the Government"'},
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.translations["AUS_political_events.16.t"] == "Nazis in the Government"

    def test_ignores_comments_and_header(self, make_localizer, hoi4_install):
        path = hoi4_install / "localisation" / "english" / "x_l_english.yml"
        path.write_text(
            "l_english:\n"
            "# this is a comment\n"
            ' GER:0 "Germany"\n'
            "  # indented comment\n",
            encoding="utf-8-sig",
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.translations == {"GER": "Germany"}

    def test_get_localized_text_falls_back_to_cleaned_key(self, make_localizer):
        loc = make_localizer()
        # No files loaded — fallback path kicks in.
        # Strips the country prefix and title-cases the rest.
        result = loc.get_localized_text("NOR_some_idea_name")
        assert result == "Some Idea Name"

    def test_dollar_variable_reference_resolves(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "leon_blum": "Léon Blum",
                "FRA_leader_name": "$leon_blum$",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.get_localized_text("FRA_leader_name") == "Léon Blum"


# ----------------------------------------------------------------------------
# Override order across base game / mods / same-named files
# ----------------------------------------------------------------------------

class TestOverrideOrder:
    def _setup_base(self, hoi4_install: Path, **kv: str) -> None:
        write_yml(
            hoi4_install / "localisation" / "english" / "countries_l_english.yml",
            kv,
        )

    def _setup_mod(self, user_dir: Path, name: str, position: int, **kv: str) -> Path:
        """Create a mod with its own countries_l_english.yml and register it
        as enabled at `position` in the active playset."""
        mod_dir = user_dir / "mods" / name
        write_yml(
            mod_dir / "localisation" / "countries_l_english.yml",
            kv,
        )
        return mod_dir

    def test_mod_overrides_base_game(self, make_localizer, hoi4_install, user_dir):
        self._setup_base(hoi4_install, SOV="Soviet Union", GER="Germany")
        mod_dir = self._setup_mod(user_dir, "KR", position=1, SOV="Russia")
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="Kaiserredux",
            mods=[
                {"display_name": "KR", "dir_path": mod_dir, "enabled": True, "position": 1},
            ],
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.translations["SOV"] == "Russia"        # mod wins
        assert loc.translations["GER"] == "Germany"       # base survives where mod is silent

    def test_later_mod_overrides_earlier_mod(self, make_localizer, hoi4_install, user_dir):
        # Two mods both touch SOV with the same filename. Later position must win.
        self._setup_base(hoi4_install, SOV="Soviet Union")
        early = self._setup_mod(user_dir, "EarlyMod", position=1, SOV="Russia")
        late = self._setup_mod(user_dir, "LateMod", position=2, SOV="Muscovy")
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="Stack",
            mods=[
                {"display_name": "EarlyMod", "dir_path": early, "enabled": True, "position": 1},
                {"display_name": "LateMod", "dir_path": late, "enabled": True, "position": 2},
            ],
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.translations["SOV"] == "Muscovy"


# ----------------------------------------------------------------------------
# Playset resolution against the launcher DB
# ----------------------------------------------------------------------------

class TestPlaysetResolution:
    def test_returns_empty_when_db_missing(self, make_localizer, user_dir):
        loc = make_localizer()
        # No launcher-v2.sqlite was written.
        assert not (user_dir / "launcher-v2.sqlite").exists()
        assert loc.resolve_active_playset_mods() == []

    def test_filters_to_active_playset_only(self, make_localizer, user_dir):
        # Mod is in the schema but not joined to the active playset.
        mod_dir = user_dir / "mods" / "Orphan"
        (mod_dir / "localisation").mkdir(parents=True)
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="ActivePS",
            mods=[
                {
                    "display_name": "Orphan",
                    "dir_path": mod_dir,
                    "enabled": True,
                    "position": 1,
                    "in_active_playset": False,
                }
            ],
        )
        loc = make_localizer()
        assert loc.resolve_active_playset_mods() == []

    def test_filters_out_disabled_mods(self, make_localizer, user_dir):
        on_dir = user_dir / "mods" / "OnMod"
        off_dir = user_dir / "mods" / "OffMod"
        (on_dir / "localisation").mkdir(parents=True)
        (off_dir / "localisation").mkdir(parents=True)
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="PS",
            mods=[
                {"display_name": "OffMod", "dir_path": off_dir, "enabled": False, "position": 1},
                {"display_name": "OnMod", "dir_path": on_dir, "enabled": True, "position": 2},
            ],
        )
        loc = make_localizer()
        result = loc.resolve_active_playset_mods()
        names = [name for name, _ in result]
        assert names == ["OnMod"]

    def test_orders_by_position(self, make_localizer, user_dir):
        dirs = []
        for name in ("A", "B", "C"):
            d = user_dir / "mods" / name
            (d / "localisation").mkdir(parents=True)
            dirs.append(d)
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="PS",
            mods=[
                # Insert deliberately out of position order.
                {"display_name": "B", "dir_path": dirs[1], "enabled": True, "position": 2},
                {"display_name": "C", "dir_path": dirs[2], "enabled": True, "position": 3},
                {"display_name": "A", "dir_path": dirs[0], "enabled": True, "position": 1},
            ],
        )
        loc = make_localizer()
        result = loc.resolve_active_playset_mods()
        assert [n for n, _ in result] == ["A", "B", "C"]

    def test_skips_mods_without_localisation_dir(self, make_localizer, user_dir):
        no_loc = user_dir / "mods" / "NoLoc"
        no_loc.mkdir(parents=True)  # No `localisation/` subfolder.
        with_loc = user_dir / "mods" / "WithLoc"
        (with_loc / "localisation").mkdir(parents=True)
        build_launcher_db(
            user_dir / "launcher-v2.sqlite",
            active_playset="PS",
            mods=[
                {"display_name": "NoLoc", "dir_path": no_loc, "enabled": True, "position": 1},
                {"display_name": "WithLoc", "dir_path": with_loc, "enabled": True, "position": 2},
            ],
        )
        loc = make_localizer()
        assert [n for n, _ in loc.resolve_active_playset_mods()] == ["WithLoc"]


# ----------------------------------------------------------------------------
# Convenience getters
# ----------------------------------------------------------------------------

class TestGetters:
    def test_get_country_name_uses_ideology_variant(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {"CAN": "Canada", "CAN_national_populist": "Kingdom of Canada"},
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.get_country_name("CAN") == "Canada"
        assert loc.get_country_name("CAN", "national_populist") == "Kingdom of Canada"

    def test_get_event_name_tries_title_suffix(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {"_RAW:1": ' some_event.1.t: "The Event"'},
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.get_event_name("some_event.1") == "The Event"

    def test_get_event_name_returns_id_when_missing(self, make_localizer):
        loc = make_localizer()
        # Hidden events that have no localization just return the raw ID.
        assert loc.get_event_name("hidden_event.99") == "hidden_event.99"

    def test_get_focus_description_returns_value_when_present(
        self, make_localizer, hoi4_install
    ):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "CAN_kings_speech": "The King's Speech",
                "CAN_kings_speech_desc": "Edward will be crowned king.",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        assert loc.get_focus_description("CAN_kings_speech") == "Edward will be crowned king."

    def test_get_focus_description_returns_empty_string_when_missing(self, make_localizer):
        loc = make_localizer()
        # Critical: must NOT fall back to a cleaned-key string. A missing
        # description is normal and should be empty so the CLI can skip it.
        assert loc.get_focus_description("CAN_no_such_focus") == ""


class TestGetCountryDisplayName:
    """The dynamic/cosmetic-aware name resolver. Captures the layered lookup
    priority that makes WHR/RUS/BAT render correctly under KR."""

    def test_cosmetic_plus_party_wins(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "WHR_BEL_syndicalist_DEF": "the Belarusian Workers' Socialist Republic",
                "WHR_BEL_DEF": "Belarus",
                "WHR_syndicalist_DEF": "Belarusian People's Republic",
                "WHR_DEF": "WHR fallback",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        assert (
            loc.get_country_display_name("WHR", cosmetic_tag="WHR_BEL", ruling_party="syndicalist")
            == "the Belarusian Workers' Socialist Republic"
        )

    def test_falls_through_to_cosmetic_only(self, make_localizer, hoi4_install):
        # Cosmetic-with-party key doesn't exist, but cosmetic alone does.
        # This is the real RUS->SOV case: SOV_syndicalist_DEF isn't defined
        # but SOV_DEF is.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "SOV_DEF": "the Russian Socialist Federative Soviet Republic",
                "RUS_syndicalist_DEF": "the Russian Republic",
                "RUS_DEF": "Russia",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        assert (
            loc.get_country_display_name("RUS", cosmetic_tag="SOV", ruling_party="syndicalist")
            == "the Russian Socialist Federative Soviet Republic"
        )

    def test_falls_through_to_tag_plus_party(self, make_localizer, hoi4_install):
        # No cosmetic data — pure ideology variant on the bare tag.
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "CAN_market_liberal_DEF": "the Kingdom of Canada",
                "CAN_DEF": "Canada",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        assert (
            loc.get_country_display_name("CAN", cosmetic_tag=None, ruling_party="market_liberal")
            == "the Kingdom of Canada"
        )

    def test_falls_through_to_bare_tag_then_def(self, make_localizer, hoi4_install):
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {"RUS": "Russia"},
        )
        loc = make_localizer()
        loc.load_all_files()
        # No party-specific key, just the bare tag — pre-existing behaviour.
        assert loc.get_country_display_name("RUS") == "Russia"

    def test_blind_fallback_globs_for_any_def_variant(self, make_localizer, hoi4_install):
        # The BAT case: no cosmetic data in the save, no plain BAT key,
        # but dozens of BAT_*_DEF variants exist. We pick the alphabetical
        # first so the result is deterministic AND readable, rather than
        # falling back to "Bat".
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "BAT_FED_paternal_autocrat_DEF": "the Baltic Federation",
                "BAT_PRI_DEF": "the General-Governorate of Pribaltika",
                "BAT_Riga_DEF": "the Commune of Riga",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        result = loc.get_country_display_name("BAT")
        # Whatever it picks, it must be one of the real values — not "Bat".
        assert result in {
            "the Baltic Federation",
            "the General-Governorate of Pribaltika",
            "the Commune of Riga",
        }

    def test_final_fallback_to_cleaned_key(self, make_localizer):
        # No keys at all for this tag — final cleaned-key behaviour kicks in.
        # _clean_key_for_display title-cases bare tags ("ZZZ" -> "Zzz").
        # Ugly but consistent with the pre-existing fallback.
        loc = make_localizer()
        assert loc.get_country_display_name("ZZZ") == "Zzz"

    def test_ignores_empty_string_lookups(self, make_localizer, hoi4_install):
        # If a localized value happens to be the empty string, treat it as
        # "missing" and continue to the next candidate. This guards against
        # KR having a stub entry that would otherwise short-circuit to "".
        write_yml(
            hoi4_install / "localisation" / "english" / "x_l_english.yml",
            {
                "_RAW:1": ' XYZ_paternal_autocrat_DEF:0 ""',
                "XYZ_DEF": "the Real Name",
            },
        )
        loc = make_localizer()
        loc.load_all_files()
        result = loc.get_country_display_name(
            "XYZ", cosmetic_tag=None, ruling_party="paternal_autocrat"
        )
        assert result == "the Real Name"
