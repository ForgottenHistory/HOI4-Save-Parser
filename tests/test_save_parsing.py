"""Tests for src/save_parsing.py."""

from __future__ import annotations

from save_parsing import (
    find_country_block,
    get_player_tag,
    parse_country_name_hints,
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
