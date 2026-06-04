"""Tests for src/save_parsing.py."""

from __future__ import annotations

from save_parsing import (
    find_country_block,
    get_game_date,
    get_player_tag,
    parse_country_name_hints,
    parse_factions,
    parse_puppet_relations,
    parse_war_relations,
    parse_wargoal_pairs,
    walk_block,
)


# ---------------------------------------------------------------------------
# walk_block
# ---------------------------------------------------------------------------

class TestWalkBlock:
    def test_handles_nested_braces(self):
        text = "{a{b}c{d{e}f}g}"
        end = walk_block(text, 1)
        assert text[1:end - 1] == "a{b}c{d{e}f}g"

    def test_returns_end_of_text_on_unclosed_block(self):
        # Truncated saves shouldn't crash — the walker just runs to EOF.
        text = "{a{b"
        end = walk_block(text, 1)
        assert end == len(text)  # depth never hit 0; bounded by len


# ---------------------------------------------------------------------------
# find_country_block — single shared primitive for both focuses and hints.
# ---------------------------------------------------------------------------

def _country_block(tag: str, body_inside: str, *, with_marker: bool = True) -> str:
    marker = "\t\truling_party=\"social_democrat\"\n" if with_marker else ""
    return f"\n\t{tag}=" + "{\n" + marker + body_inside + "\n\t}\n"


class TestFindCountryBlock:
    def test_returns_body_of_real_country(self):
        save = "header" + _country_block("CAN", "\t\tstability=0.8")
        body = find_country_block(save, "CAN")
        assert body is not None
        assert "ruling_party=" in body
        assert "stability=0.8" in body

    def test_returns_none_for_missing_tag(self):
        save = "header" + _country_block("GER", "\t\tstability=0.5")
        assert find_country_block(save, "CAN") is None

    def test_skips_diplomatic_relation_block_with_same_tag(self):
        # Diplomatic-relation entries also start \n\tCAN={ but lack
        # focus_tree= / ruling_party=.
        relation = "\n\tCAN={\n\t\ttype=2\n\t\tfrom_state=44\n\t}\n"
        country = _country_block("CAN", "\t\tstability=0.8")
        save = "x" + relation + country
        body = find_country_block(save, "CAN")
        assert body is not None
        assert "stability=0.8" in body  # picked the country, not the relation


# ---------------------------------------------------------------------------
# parse_country_name_hints
# ---------------------------------------------------------------------------

class TestParseCountryNameHints:
    def test_extracts_cosmetic_tag_and_ruling_party(self):
        body = (
            '\t\truling_party="syndicalist"\n'
            '\t\tcosmetic_tag="WHR_BEL"\n'
        )
        save = "x" + _country_block("WHR", body, with_marker=False)
        hints = parse_country_name_hints(save)
        assert hints == {
            "WHR": {"cosmetic_tag": "WHR_BEL", "ruling_party": "syndicalist"},
        }

    def test_empty_cosmetic_tag_becomes_none(self):
        # HOI4 writes `cosmetic_tag=""` for countries with no override.
        # That must map to None so the lookup falls back to the tag itself.
        body = (
            '\t\truling_party="paternal_autocrat"\n'
            '\t\tcosmetic_tag=""\n'
        )
        save = "x" + _country_block("RUS", body, with_marker=False)
        hints = parse_country_name_hints(save)
        assert hints == {
            "RUS": {"cosmetic_tag": None, "ruling_party": "paternal_autocrat"},
        }

    def test_missing_fields_are_none(self):
        body = "\t\tstability=0.5\n"
        # Force inclusion as a real country block via the focus_tree= marker.
        body_with_marker = '\t\tfocus_tree="canada_focus"\n' + body
        save = "x" + _country_block("CAN", body_with_marker, with_marker=False)
        hints = parse_country_name_hints(save)
        assert hints == {
            "CAN": {"cosmetic_tag": None, "ruling_party": None},
        }

    def test_skips_diplomatic_relation_entries(self):
        # The save has a CAN={...} that's a relation entry, no real CAN
        # country block. We get an empty result, not a malformed entry.
        save = "x\n\tCAN={\n\t\ttype=2\n\t\tfrom_state=44\n\t}\n"
        assert parse_country_name_hints(save) == {}

    def test_multiple_countries(self):
        save = (
            "header"
            + _country_block(
                "GER",
                '\t\truling_party="authoritarian_democrat"\n'
                '\t\tcosmetic_tag=""\n',
                with_marker=False,
            )
            + _country_block(
                "FRA",
                '\t\truling_party="syndicalist"\n'
                '\t\tcosmetic_tag="FRA_CFR"\n',
                with_marker=False,
            )
        )
        hints = parse_country_name_hints(save)
        assert hints["GER"] == {"cosmetic_tag": None, "ruling_party": "authoritarian_democrat"}
        assert hints["FRA"] == {"cosmetic_tag": "FRA_CFR", "ruling_party": "syndicalist"}


# ---------------------------------------------------------------------------
# get_player_tag
# ---------------------------------------------------------------------------

class TestGetPlayerTag:
    def test_extracts_tag_from_save_header(self):
        save = (
            'HOI4txt\n'
            'player="CAN"\n'
            'ideology=national_populist\n'
            'date="1946.5.28.24"\n'
        )
        assert get_player_tag(save) == "CAN"

    def test_returns_none_when_missing(self):
        assert get_player_tag("HOI4txt\nno player field here") is None

    def test_ignores_player_substrings_deeper_in_save(self):
        # The save has tons of fields containing "player" (player_countries=,
        # player_id=, etc.) and other `player=` lines deep inside character
        # or decision blocks. We must only match the top-level header.
        save = (
            'HOI4txt\n'
            'player="WRA"\n'
            'date="1936.7.19.1"\n'
            'player_countries={\n'
            '\tWRA={\n'
            '\t\tuser="Meanie"\n'
            '\t}\n'
            '}\n'
            'some_block={\n'
            '\tplayer="FAKE"\n'   # indented — must be ignored
            '}\n'
        )
        assert get_player_tag(save) == "WRA"


# ---------------------------------------------------------------------------
# get_game_date
# ---------------------------------------------------------------------------

class TestGetGameDate:
    def test_parses_components_and_raw(self):
        save = 'HOI4txt\nplayer="CAN"\ndate="1946.5.28.24"\nrest\n'
        assert get_game_date(save) == {
            "year": 1946, "month": 5, "day": 28, "hour": 24,
            "raw": "1946.5.28.24",
        }

    def test_single_digit_components(self):
        # HOI4 does NOT zero-pad — start of game is 1936.1.1.12 not 1936.01.01.12.
        save = 'HOI4txt\ndate="1936.1.1.1"\n'
        d = get_game_date(save)
        assert d["month"] == 1 and d["day"] == 1 and d["hour"] == 1
        assert d["raw"] == "1936.1.1.1"

    def test_returns_none_when_missing(self):
        assert get_game_date("HOI4txt\nplayer=\"CAN\"\n") is None

    def test_ignores_date_lines_deeper_in_save(self):
        # `date="..."` shows up inside war blocks, character birthdays,
        # last_election fields, etc. Only the anchored header date is the
        # game's current date.
        save = (
            'HOI4txt\n'
            'date="1946.5.28.24"\n'
            'wars={\n'
            '\twar={\n'
            '\t\tdate="1939.9.1.12"\n'   # not the game date
            '\t}\n'
            '}\n'
        )
        d = get_game_date(save)
        assert d["raw"] == "1946.5.28.24"


# ---------------------------------------------------------------------------
# parse_factions
# ---------------------------------------------------------------------------

def _faction_block(name: str, ideology: str, members: list[str]) -> str:
    mem = "\n".join(f'\t\t"{m}"' for m in members)
    return (
        "\nfaction={\n"
        f'\tname="{name}"\n'
        f"\tideology={ideology}\n"
        "\tmembers={\n"
        f"{mem}\n"
        "\t}\n"
        "}\n"
    )


class TestParseFactions:
    def test_extracts_basic_fields(self):
        save = "header" + _faction_block("Entente", "national_populist", ["CAN", "AST"])
        facts = parse_factions(save)
        assert len(facts) == 1
        assert facts[0]["name"] == "Entente"
        assert facts[0]["ideology"] == "national_populist"
        assert facts[0]["members"] == ["CAN", "AST"]

    def test_multiple_factions(self):
        save = (
            "x"
            + _faction_block("Entente", "national_populist", ["CAN"])
            + _faction_block("Reichspakt", "authoritarian_democrat", ["GER", "BEL"])
        )
        facts = parse_factions(save)
        names = [f["name"] for f in facts]
        assert names == ["Entente", "Reichspakt"]

    def test_empty_members_returns_empty_list(self):
        save = (
            "\nfaction={\n"
            '\tname="Stub"\n'
            "\tideology=collectivist\n"
            "\tmembers={\n\t}\n"
            "}\n"
        )
        facts = parse_factions(save)
        assert facts[0]["members"] == []


# ---------------------------------------------------------------------------
# parse_puppet_relations
# ---------------------------------------------------------------------------

class TestParsePuppetRelations:
    def test_extracts_overlord_and_subject(self):
        save = (
            'header\n'
            'puppet={\n'
            '\tautonomy_state="kr_occupied_puppet"\n'
            '\tfirst="CAN"\n'
            '\tsecond="BAY"\n'
            '\tstart_date="1946.5.11.3"\n'
            '}\n'
        )
        rels = parse_puppet_relations(save)
        assert rels == [{
            "overlord": "CAN",
            "subject": "BAY",
            "autonomy_state": "kr_occupied_puppet",
            "start_date": "1946.5.11.3",
        }]

    def test_dedups_mirrored_relations(self):
        # The same overlord/subject pair appears in both countries'
        # active_relations blocks. We expect a single record.
        block = (
            'puppet={\n'
            '\tautonomy_state="kr_initial_wif_puppet"\n'
            '\tfirst="CAN"\n'
            '\tsecond="CAF"\n'
            '\tstart_date="1943.12.22.14"\n'
            '}\n'
        )
        save = "x" + block + "more text" + block
        rels = parse_puppet_relations(save)
        assert len(rels) == 1

    def test_missing_start_date_is_none(self):
        save = (
            'puppet={\n'
            '\tautonomy_state="kr_dominion"\n'
            '\tfirst="GBR"\n'
            '\tsecond="IND"\n'
            '}\n'
        )
        rels = parse_puppet_relations(save)
        assert rels[0]["start_date"] is None


# ---------------------------------------------------------------------------
# parse_wargoal_pairs
# ---------------------------------------------------------------------------

class TestParseWargoalPairs:
    def test_extracts_actor_recipient_pair(self):
        save = (
            'wargoals={\n'
            '\tannex_everything={\n'
            '\t\tid={ id=1 type=4713 }\n'
            '\t\twargoaldata_actor="CAN"\n'
            '\t\twargoaldata_recipient="GER"\n'
            '\t\ttype=annex_everything\n'
            '\t}\n'
            '}\n'
        )
        assert parse_wargoal_pairs(save) == [{"actor": "CAN", "recipient": "GER"}]

    def test_multiple_wargoals_preserved_in_order(self):
        save = (
            'wargoaldata_actor="CAN"\nwargoaldata_recipient="ENG"\n'
            'wargoaldata_actor="RUS"\nwargoaldata_recipient="WRA"\n'
            'wargoaldata_actor="CAN"\nwargoaldata_recipient="GER"\n'
        )
        pairs = parse_wargoal_pairs(save)
        assert pairs == [
            {"actor": "CAN", "recipient": "ENG"},
            {"actor": "RUS", "recipient": "WRA"},
            {"actor": "CAN", "recipient": "GER"},
        ]

    def test_returns_empty_when_no_wargoals(self):
        assert parse_wargoal_pairs("HOI4txt\nplayer=\"CAN\"\n") == []


# ---------------------------------------------------------------------------
# parse_war_relations
# ---------------------------------------------------------------------------

def _war_relation_block(
    first: str,
    second: str,
    *,
    start: str = "1936.7.18.12",
    instigator: str = "yes",
    defender_reason: str = "war",
) -> str:
    return (
        "war_relation={\n"
        f'\tfirst="{first}"\n'
        f'\tsecond="{second}"\n'
        f'\tstart_date="{start}"\n'
        f"\tfirst_was_instigator={instigator}\n"
        f"\thostility_reason_instigator=war\n"
        f"\thostility_reason_defender={defender_reason}\n"
        "}\n"
    )


class TestParseWarRelations:
    def test_extracts_instigator_and_defender(self):
        save = "x" + _war_relation_block("RUS", "WRA", start="1936.7.18.12")
        wars = parse_war_relations(save)
        assert wars == [{
            "instigator": "RUS",
            "defender": "WRA",
            "start_date": "1936.7.18.12",
            "first_was_instigator": True,
        }]

    def test_skips_non_war_hostility(self):
        # Puppet relationships sometimes use the same envelope but with
        # hostility_reason_defender=puppet — those aren't wars.
        save = (
            "x"
            + _war_relation_block("RUS", "WRA")
            + _war_relation_block("ORE", "RUS", defender_reason="puppet")
        )
        wars = parse_war_relations(save)
        assert len(wars) == 1
        assert wars[0]["defender"] == "WRA"

    def test_first_was_instigator_false_when_no(self):
        save = "x" + _war_relation_block("FIN", "RUS", instigator="no")
        wars = parse_war_relations(save)
        assert wars[0]["first_was_instigator"] is False

    def test_multiple_wars(self):
        save = (
            "x"
            + _war_relation_block("RUS", "KAR", start="1936.5.1.24")
            + _war_relation_block("RUS", "WRA", start="1936.7.18.12")
            + _war_relation_block("FIN", "RUS", start="1936.5.2.24", instigator="no")
        )
        wars = parse_war_relations(save)
        pairs = [(w["instigator"], w["defender"]) for w in wars]
        assert pairs == [("RUS", "KAR"), ("RUS", "WRA"), ("FIN", "RUS")]

    def test_returns_empty_when_no_wars(self):
        assert parse_war_relations("HOI4txt\nplayer=\"CAN\"\n") == []
