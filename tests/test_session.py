"""Tests for src/hoi4_session.py.

The session class has a real lifecycle: signature-based refresh, lazy
caches, eager localizer. Tests cover each transition.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from conftest import write_yml

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from hoi4_session import HOI4Session
from save_locator import find_autosave_path


# ---------------------------------------------------------------------------
# Synthetic save and localizer setup
# ---------------------------------------------------------------------------

def _minimal_save(tag: str = "CAN", *, ruling_party: str = "national_populist") -> str:
    """Smallest valid-looking country block the session can query against."""
    return (
        'HOI4txt\nplayer="CAN"\n'
        f'\n\t{tag}=' + "{\n"
        '\t\tfocus_tree="canada_focus"\n'
        f'\t\truling_party="{ruling_party}"\n'
        '\t\tcosmetic_tag=""\n'
        "\t\tpolitics={\n"
        "\t\t\tparties={\n"
        f"\t\t\t\t{ruling_party}=" + "{\n"
        "\t\t\t\t\tpopularity=60.0\n"
        "\t\t\t\t\tcountry_leader={\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\tideas={ civilian_economy }\n"
        "\t\t}\n"
        "\t}\n"
    )


@pytest.fixture
def session_save(tmp_path):
    """Path to a synthetic autosave on disk."""
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    save_path = saves_dir / "autosave.hoi4"
    save_path.write_text(_minimal_save(), encoding="utf-8")
    return save_path


@pytest.fixture
def session(make_localizer, hoi4_install, session_save):
    """A session pointed at a synthetic save, with locale seeded.

    We skip the eager localizer load and inject a pre-built one so the
    test stays fast and hermetic instead of trying to load the real
    HOI4 install.
    """
    write_yml(
        hoi4_install / "localisation" / "english" / "x_l_english.yml",
        {
            "CAN": "Canada",
            "CAN_national_populist_DEF": "the Kingdom of Canada",
            "CAN_national_populist_party": "IUP",
            "CAN_national_populist_party_long": "Imperial Unity Party",
            "civilian_economy": "Civilian Economy",
        },
    )
    loc = make_localizer()
    loc.load_all_files()

    s = HOI4Session(save_path=session_save, load_localizer=False)
    s.localizer = loc
    return s


# ---------------------------------------------------------------------------
# Lifecycle: refresh + cache invalidation
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_first_refresh_loads_save(self, session, session_save):
        assert session.is_loaded is False
        assert session.refresh() is True
        assert session.is_loaded is True
        assert session.current_signature is not None

    def test_second_refresh_with_no_change_returns_false_and_no_reread(
        self, session
    ):
        session.refresh()
        text_before = session.save_text
        assert session.refresh() is False
        # Identity check: cached save_text wasn't replaced.
        assert session.save_text is text_before

    def test_refresh_returns_false_when_save_missing(self, tmp_path):
        # Point at a path that doesn't exist; refresh must not raise and
        # must report False so a polling daemon can keep going.
        s = HOI4Session(save_path=tmp_path / "nope.hoi4", load_localizer=False)
        assert s.refresh() is False
        assert s.is_loaded is False

    def test_signature_change_triggers_reread(self, session, session_save):
        session.refresh()
        sig1 = session.current_signature

        # Modify the file — both size and mtime change.
        session_save.write_text(_minimal_save(tag="GER"), encoding="utf-8")
        # Some filesystems have second-resolution mtime; nudge it.
        os.utime(session_save, (sig1[0] + 2, sig1[0] + 2))

        assert session.refresh() is True
        assert session.current_signature != sig1


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------

class TestCacheBehavior:
    def test_per_tag_queries_cache_within_same_save(self, session):
        session.refresh()
        a = session.country_leader("CAN")
        b = session.country_leader("CAN")
        # Same object: result was cached, not recomputed.
        assert a is b

    def test_caches_cleared_on_refresh(self, session, session_save):
        session.refresh()
        first = session.country_leader("CAN")

        # Rewrite the save (different content -> different signature).
        new_text = _minimal_save(tag="CAN", ruling_party="paternal_autocrat")
        session_save.write_text(new_text, encoding="utf-8")
        os.utime(session_save, (session.current_signature[0] + 2,) * 2)

        session.refresh()
        second = session.country_leader("CAN")
        # New result reflects the new ruling party. (Even if leader is
        # None, the result identity differs because the cache was cleared.)
        assert first is not second
        assert second["ruling_party_id"] == "paternal_autocrat"

    def test_save_wide_parses_built_lazily_once(self, session):
        session.refresh()
        chars1 = session.characters
        chars2 = session.characters
        # Same dict object — built once and cached on the session.
        assert chars1 is chars2


# ---------------------------------------------------------------------------
# Query pass-through
# ---------------------------------------------------------------------------

class TestQueryPassthrough:
    def test_player_tag_from_save_header(self, session):
        session.refresh()
        # The synthetic save fixture writes `player="CAN"` in the header.
        assert session.player_tag == "CAN"

    def test_game_date_from_save_header(self, session, session_save):
        # Synthetic save doesn't include date= by default, so add one.
        # The fixture writes player="CAN" first; we prepend a date line.
        text = session_save.read_text(encoding="utf-8")
        session_save.write_text(
            text.replace('player="CAN"\n', 'player="CAN"\ndate="1946.5.28.24"\n'),
            encoding="utf-8",
        )
        # Force refresh to see the new content (and update signature).
        import os
        sig = session.current_signature
        if sig is not None:
            os.utime(session_save, (sig[0] + 2, sig[0] + 2))
        session.refresh()
        d = session.game_date
        assert d == {
            "year": 1946, "month": 5, "day": 28, "hour": 24,
            "raw": "1946.5.28.24",
        }

    def test_country_display_name_uses_hints(self, session):
        session.refresh()
        # ruling_party hint from the save drives the lookup priority,
        # picking the *_national_populist_DEF variant from our locale.
        assert session.country_display_name("CAN") == "the Kingdom of Canada"

    def test_country_parties_returns_structured_data(self, session):
        session.refresh()
        parties = session.country_parties("CAN")
        assert parties is not None
        assert parties[0]["id"] == "national_populist"
        assert parties[0]["short"] == "IUP"
        assert parties[0]["is_ruling"] is True

    def test_country_ideas_caches_separately_per_include_hidden(self, session):
        session.refresh()
        visible = session.country_ideas("CAN", include_hidden=False)
        with_hidden = session.country_ideas("CAN", include_hidden=True)
        # Same content here (no hidden ideas in the synthetic save) but
        # the cache key is distinct — second call doesn't return the
        # first cached object.
        assert visible is not with_hidden


# ---------------------------------------------------------------------------
# Diplomacy queries
# ---------------------------------------------------------------------------

def _diplomacy_save(tag: str = "CAN") -> str:
    """Synthetic save with a faction, a puppet, wargoals, and active wars.

    The wargoals and the active wars deliberately don't match each other —
    CAN has wargoals against GER (stale, no current war) but is actively
    at war with ENG (no wargoal record because none was needed). This
    mirrors what real KR saves do: wargoals persist after peace, and the
    engine sometimes starts wars without a long-lived wargoal record.
    """
    # The country block has enough structure for find_country_block to accept it
    # (focus_tree=), nothing else matters for the diplomacy queries — those
    # scan the whole save text.
    return (
        'HOI4txt\nplayer="CAN"\n'
        # CAN country block (just enough to be recognised)
        '\n\tCAN={\n'
        '\t\tfocus_tree="canada_focus"\n'
        '\t\truling_party="social_liberal"\n'
        '\t}\n'
        # Faction
        '\nfaction={\n'
        '\tname="Entente"\n'
        '\tideology=social_liberal\n'
        '\tmembers={\n'
        '\t\t"CAN"\n\t\t"AST"\n\t\t"NFL"\n'
        '\t}\n'
        '}\n'
        # Puppet relation (CAN overlord of BAY)
        'puppet={\n'
        '\tautonomy_state="kr_occupied_puppet"\n'
        '\tfirst="CAN"\n'
        '\tsecond="BAY"\n'
        '\tstart_date="1946.5.11.3"\n'
        '}\n'
        # Wargoals: stale (CAN-GER) — no active war for either
        'wargoaldata_actor="CAN"\nwargoaldata_recipient="GER"\n'
        # Active wars: CAN attacking ENG, RUS attacking CAN
        'war_relation={\n'
        '\tfirst="CAN"\n\tsecond="ENG"\n'
        '\tstart_date="1946.1.2.3"\n'
        '\tfirst_was_instigator=yes\n'
        '\thostility_reason_instigator=war\n'
        '\thostility_reason_defender=war\n'
        '}\n'
        'war_relation={\n'
        '\tfirst="RUS"\n\tsecond="CAN"\n'
        '\tstart_date="1946.2.4.5"\n'
        '\tfirst_was_instigator=yes\n'
        '\thostility_reason_instigator=war\n'
        '\thostility_reason_defender=war\n'
        '}\n'
    )


@pytest.fixture
def diplomacy_session(session_save, hoi4_install, make_localizer):
    """Session pointed at a save containing faction/puppet/war state."""
    session_save.write_text(_diplomacy_save(), encoding="utf-8")
    loc = make_localizer()  # empty locale is fine — diplomacy queries don't use it
    loc.load_all_files()
    s = HOI4Session(save_path=session_save, load_localizer=False)
    s.localizer = loc
    s.refresh()
    return s


class TestDiplomacyQueries:
    def test_country_faction_returns_membership(self, diplomacy_session):
        f = diplomacy_session.country_faction("CAN")
        assert f["name"] == "Entente"
        assert "CAN" in f["members"]
        assert "AST" in f["members"]

    def test_country_faction_returns_none_when_unaligned(self, diplomacy_session):
        # GER isn't a member of the synthetic Entente.
        assert diplomacy_session.country_faction("GER") is None

    def test_country_subjects_lists_puppets(self, diplomacy_session):
        subs = diplomacy_session.country_subjects("CAN")
        assert len(subs) == 1
        assert subs[0]["subject"] == "BAY"
        assert subs[0]["autonomy_state"] == "kr_occupied_puppet"

    def test_country_overlord_for_subject(self, diplomacy_session):
        over = diplomacy_session.country_overlord("BAY")
        assert over is not None
        assert over["overlord"] == "CAN"

    def test_country_overlord_none_for_sovereign(self, diplomacy_session):
        assert diplomacy_session.country_overlord("CAN") is None

    def test_country_wars_reflects_active_wars_only(self, diplomacy_session):
        # CAN's only active wars are ENG (offensive) and RUS (defensive).
        # The CAN→GER wargoal in the save is stale and must NOT appear
        # under country_wars (that's the bug from the wargoals-only impl).
        wars = diplomacy_session.country_wars("CAN")
        assert wars == {"attacking": ["ENG"], "attacked_by": ["RUS"]}

    def test_country_wars_attacker_side_only(self, diplomacy_session):
        # ENG is in the save as the defender against CAN.
        wars = diplomacy_session.country_wars("ENG")
        assert wars == {"attacking": [], "attacked_by": ["CAN"]}

    def test_country_wargoals_separate_from_wars(self, diplomacy_session):
        # The stale CAN→GER wargoal IS visible through country_wargoals,
        # which surfaces justifications (not active wars).
        wg = diplomacy_session.country_wargoals("CAN")
        assert wg == {"as_actor": ["GER"], "as_recipient": []}

    def test_diplomacy_caches_are_save_wide(self, diplomacy_session):
        # All save-wide caches are built once and reused.
        a = diplomacy_session.factions
        b = diplomacy_session.factions
        assert a is b
        c = diplomacy_session.puppet_relations
        assert c is diplomacy_session.puppet_relations
        d = diplomacy_session.wargoals
        assert d is diplomacy_session.wargoals
        e = diplomacy_session.wars
        assert e is diplomacy_session.wars


# ---------------------------------------------------------------------------
# Localizer construction
# ---------------------------------------------------------------------------

class TestLocalizerLoading:
    def test_load_localizer_false_defers_load(self, tmp_path, monkeypatch):
        # Verify the lazy-load contract: with load_localizer=False, no
        # localizer instance exists until ensure_localizer() is called.
        # We don't actually trigger the real load — that would hit disk.
        s = HOI4Session(
            save_path=tmp_path / "x.hoi4",
            load_localizer=False,
        )
        assert s.localizer is None

    def test_save_text_property_raises_before_refresh(self, tmp_path):
        s = HOI4Session(save_path=tmp_path / "x.hoi4", load_localizer=False)
        with pytest.raises(RuntimeError):
            _ = s.save_text
