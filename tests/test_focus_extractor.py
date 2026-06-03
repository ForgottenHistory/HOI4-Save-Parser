"""Tests for scripts/list_country_focuses.py.

Focus extraction is pure string parsing, so tests assemble small synthetic save
fragments and check that the right substring comes back. The realistic edge
cases (relation blocks with matching tags, nested braces, missing focus block)
are exactly the things that quietly broke during development.
"""

from __future__ import annotations

import re

from list_country_focuses import _walk_block, find_country_focus_block


def _country_block(tag: str, focus_body: str, extra: str = "ruling_party=foo") -> str:
    """Assemble a country-block fragment that looks like the real save format:
    `\\n\\t<TAG>={ ... \\n\\t\\tfocus={ ... } ... }`. Includes a `ruling_party=`
    line so the extractor recognises it as a real country block."""
    return (
        f"\n\t{tag}=" + "{\n"
        f"\t\t{extra}\n"
        f"\t\tfocus=" + "{\n"
        f"{focus_body}\n"
        "\t\t}\n"
        "\t}\n"
    )


# ----------------------------------------------------------------------------
# _walk_block — the brace counter that backs everything else.
# ----------------------------------------------------------------------------

class TestWalkBlock:
    def test_handles_flat_block(self):
        text = "{abc}"
        # Caller has already consumed the opening '{', so we start at 1.
        end = _walk_block(text, 1)
        assert text[1:end - 1] == "abc"

    def test_handles_nested_braces(self):
        text = "{outer{inner}more}TAIL"
        end = _walk_block(text, 1)
        assert text[1:end - 1] == "outer{inner}more"
        # And the tail is still there after the matched close.
        assert text[end:] == "TAIL"

    def test_handles_multiple_nestings(self):
        text = "{a{b{c}d}e}"
        end = _walk_block(text, 1)
        assert text[1:end - 1] == "a{b{c}d}e"


# ----------------------------------------------------------------------------
# find_country_focus_block — the function the script actually exports.
# ----------------------------------------------------------------------------

class TestFindCountryFocusBlock:
    def test_extracts_completed_focuses(self):
        focus = (
            '\t\t\tcompleted="CAN_kings_speech"\n'
            '\t\t\tcompleted="CAN_crown_corporations"\n'
            '\t\t\tcurrent="CAN_in_progress_focus"'
        )
        save = "header\n" + _country_block("CAN", focus)

        block = find_country_focus_block(save, "CAN")
        assert block is not None
        completed = re.findall(r'completed="([^"]+)"', block)
        assert completed == ["CAN_kings_speech", "CAN_crown_corporations"]
        current = re.search(r'current="([^"]+)"', block)
        assert current and current.group(1) == "CAN_in_progress_focus"

    def test_returns_none_for_missing_tag(self):
        save = "header\n" + _country_block("GER", '\t\t\tcompleted="GER_x"')
        assert find_country_focus_block(save, "CAN") is None

    def test_returns_empty_string_when_country_has_no_focus_block(self):
        # A country block that exists but lacks `\n\t\tfocus={` returns ''.
        # That's the contract: None = no country, '' = country but no focus tree.
        save = "header\n\tCAN={\n\t\truling_party=foo\n\t\tstability=0.5\n\t}\n"
        assert find_country_focus_block(save, "CAN") == ""

    def test_ignores_relation_block_with_matching_tag(self):
        # Diplomatic relation blocks also start with `\n\tCAN={` but lack the
        # country-block markers (`focus_tree=` / `ruling_party=`). They must
        # not be returned, otherwise we'd pick a relation's empty focus block.
        relation = (
            "\n\tCAN={\n"
            "\t\ttype=2\n"
            "\t\tfrom_state=44\n"
            "\t\tto_state=126\n"
            "\t}\n"
        )
        country = _country_block("CAN", '\t\t\tcompleted="CAN_real_focus"')
        save = "header" + relation + country

        block = find_country_focus_block(save, "CAN")
        assert block is not None
        assert 'completed="CAN_real_focus"' in block

    def test_brace_walk_survives_nested_blocks_inside_focus(self):
        # Real focus blocks contain nested structures like priority={ ... }
        # and selected_focus_palette={ ... }. The extractor must walk past
        # them and find the *outer* focus block's close, not a nested one.
        focus = (
            '\t\t\tcompleted="CAN_a"\n'
            "\t\t\tnested_thing={\n"
            "\t\t\t\tinner_key=value\n"
            "\t\t\t\tdeeper={\n"
            "\t\t\t\t\tx=1\n"
            "\t\t\t\t}\n"
            "\t\t\t}\n"
            '\t\t\tcompleted="CAN_b"'
        )
        save = "header\n" + _country_block("CAN", focus)
        block = find_country_focus_block(save, "CAN")
        assert block is not None
        completed = re.findall(r'completed="([^"]+)"', block)
        assert completed == ["CAN_a", "CAN_b"]
        # And the nested structure is still intact in the returned body.
        assert "nested_thing={" in block
        assert "deeper={" in block
