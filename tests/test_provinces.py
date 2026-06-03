"""Tests for province-ownership extraction.

Covers compute_country_provinces — the pure composition layer. The
high-level get_country_provinces is a thin wrapper that combines I/O
helpers tested elsewhere (parse_state_files, parse_state_owners), so
we don't repeat I/O tests here.
"""

from __future__ import annotations

from map_data import compute_country_provinces


class TestComputeCountryProvinces:
    def test_returns_states_owned_by_tag(self):
        state_owners = {1: "WRA", 2: "RUS", 3: "WRA", 4: "WHR"}
        state_to_provs = {1: {10, 11}, 2: {20}, 3: {30}, 4: {40}}
        result = compute_country_provinces("WRA", state_owners, state_to_provs)
        assert result == {1: {10, 11}, 3: {30}}

    def test_returns_empty_dict_when_tag_owns_nothing(self):
        state_owners = {1: "RUS", 2: "RUS"}
        state_to_provs = {1: {10}, 2: {20}}
        # GER isn't in state_owners at all.
        assert compute_country_provinces("GER", state_owners, state_to_provs) == {}

    def test_skips_states_with_no_definition_file(self):
        # The save can reference a state ID that the mod-aware state files
        # don't currently define (e.g. an obsolete ID from a prior playset).
        # That state must not appear in the result rather than crashing or
        # surfacing as an empty province set.
        state_owners = {1: "WRA", 99: "WRA"}
        state_to_provs = {1: {10}}  # state 99 has no file
        result = compute_country_provinces("WRA", state_owners, state_to_provs)
        assert result == {1: {10}}

    def test_provinces_grouped_per_state_not_flattened(self):
        # State boundaries matter for display ("which states does CAN own"
        # vs just a flat province list). The shape must keep them separate
        # even if two states have identical province sets.
        state_owners = {1: "WRA", 2: "WRA"}
        state_to_provs = {1: {10, 11}, 2: {10, 11}}
        result = compute_country_provinces("WRA", state_owners, state_to_provs)
        assert result == {1: {10, 11}, 2: {10, 11}}
