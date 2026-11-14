import json
import os
from pathlib import Path
import subprocess

import pytest

from config import FoulPlayConfig
from data.pkmn_sets import PokemonSpread, SmogonSets, _SmogonSets
from fp.battle import Battle, Battler
from fp.helpers import normalize_name
from fp.search.main import get_battles_for_team_preview, sample_unrevealed_pkmn
from fp.search.poke_engine_helpers import battle_to_poke_engine_state
from teams.team_converter import packed_to_dict

NAMES = ["gholdengo", "raichu", "pawmot", "rillaboom", "garchomp", "dragonite"]
NATURES = ["modest", "timid", "jolly", "adamant", "jolly", "adamant"]
ITEMS = [
    "lifeorb",
    "focussash",
    "sitrusberry",
    "miracleseed",
    "garchompite",
    "leftovers",
]
ABILITY = [
    "goodasgold",
    "lightningrod",
    "ironfist",
    "grassysurge",
    "roughskin",
    "multiscale",
]
MOVES = [
    ["makeitrain", "shadowball", "nastyplot", "protect"],
    ["fakeout", "zapcannon", "focusblast", "protect"],
    ["revivalblessing", "doubleshock", "closecombat", "fakeout"],
    ["fakeout", "woodhammer", "grassyglide", "protect"],
    ["earthquake", "dragonclaw", "rockslide", "protect"],
    ["extremespeed", "dragonclaw", "icespinner", "protect"],
]
EVS = (0, 0, 0, 252, 4, 252)


def sheet(natures=NATURES):
    # As emitted by Champions: nature is present, EVs/IVs/Tera are absent.
    return "]".join(
        "|".join(
            [n, "", item, ability, ",".join(moves), nature, "", "", "", "", "50", ""]
        )
        for n, item, ability, moves, nature in zip(
            NAMES, ITEMS, ABILITY, MOVES, natures
        )
    )


def loaded_battle():
    b = Battle("battle-test")
    b.generation = "gen9"
    b.team_preview = True
    b.user.from_packed_string(sheet())
    b.opponent.from_packed_string(sheet())
    return b


def test_sheet_records_public_information_without_claiming_brought_pokemon():
    side = Battler("2")
    side.from_packed_string(sheet())
    for i, p in enumerate(side.reserve):
        assert p.name == NAMES[i]
        assert p.nature == p.known_nature == NATURES[i]
        assert p.item == ITEMS[i]
        assert p.item_known
        assert p.ability == ABILITY[i]
        assert [m.name for m in p.moves] == MOVES[i]
        assert not p.revealed  # Six visible sets do not reveal which four were brought.


def test_missing_nature_remains_unknown_and_blank_level_defaults_to_100():
    packed = sheet([""] * 6)
    data = packed_to_dict(packed)
    assert all(p["nature"] is None for p in data)
    assert all(p["tera_type"] == "" for p in data)
    side = Battler("2")
    side.from_packed_string(packed)
    assert all(p.known_nature is None for p in side.reserve)
    fields = packed.split("]")[0].split("|")
    fields[10] = ""
    assert packed_to_dict("|".join(fields))[0]["level"] == 100


def test_known_nature_cannot_be_overwritten_by_spread_inference():
    p = loaded_battle().opponent.reserve[0]
    p.set_spread("adamant", EVS)
    assert p.nature == "modest"
    assert p.evs == EVS
    assert p.item == "lifeorb"
    assert p.ability == "goodasgold"
    assert [m.name for m in p.moves] == MOVES[0]
    assert p.stats["special-attack"] > p.stats["attack"]


def test_sampling_prefers_observed_nature_over_conflicting_usage(monkeypatch):
    p = loaded_battle().opponent.reserve[0]
    manager = _SmogonSets()
    actual = PokemonSpread("modest", EVS, 1)
    guessed = PokemonSpread("timid", (252, 0, 0, 252, 4, 0), 100000)
    monkeypatch.setattr(manager, "get_pokemon_from_sets", lambda _: [guessed, actual])
    for _ in range(5):
        result = manager.get_random_spread(p)
        assert result.nature == "modest"
        assert result.evs == EVS


def test_missing_usage_nature_samples_hidden_evs_with_known_nature(monkeypatch):
    p = loaded_battle().opponent.reserve[0]
    manager = _SmogonSets()
    monkeypatch.setattr(
        manager, "get_pokemon_from_sets", lambda _: [PokemonSpread("timid", EVS, 10)]
    )
    result = manager.get_random_spread(p)
    assert result.nature == "modest"
    assert result.evs == EVS
    assert not PokemonSpread("timid", EVS, 10).spread_makes_sense(p)


def check_native_pokemon(native, expected_index):
    assert native.id == NAMES[expected_index]
    assert native.nature == NATURES[expected_index]
    assert native.item == ITEMS[expected_index]
    assert native.ability == ABILITY[expected_index]
    assert [m.id for m in native.moves] == MOVES[expected_index]


def test_preview_and_battle_mcts_states_preserve_all_sheet_facts(monkeypatch):
    monkeypatch.setattr(FoulPlayConfig, "pokemon_format", "gen9championsvgc2026regmc")
    # Even a sampler returning a conflicting nature cannot overwrite public facts.
    monkeypatch.setattr(
        SmogonSets, "get_random_spread", lambda _: PokemonSpread("bold", EVS, 1)
    )
    b = loaded_battle()
    previews = get_battles_for_team_preview(b, 2)
    for sampled, chance in previews:
        assert chance == 0.5
        state = battle_to_poke_engine_state(sampled)
        for i, native in enumerate(state.side_two.pokemon):
            check_native_pokemon(native, i)
    live = previews[0][0]
    live.team_preview = False
    original_state = battle_to_poke_engine_state(live).to_string()
    for sampled, chance in sample_unrevealed_pkmn(live, 4):
        assert chance == 0.25
        state = battle_to_poke_engine_state(sampled)
        for native in state.side_two.pokemon[:4]:
            check_native_pokemon(native, NAMES.index(native.id))
        assert len(sampled.opponent.reserve) == 2
    assert battle_to_poke_engine_state(live).to_string() == original_state
    assert len(live.opponent.reserve) == 4
    assert [p.nature for p in b.opponent.reserve] == NATURES


def test_native_mcts_opponent_actions_use_the_sheet_moves(monkeypatch):
    from poke_engine import monte_carlo_tree_search

    monkeypatch.setattr(FoulPlayConfig, "pokemon_format", "gen9championsvgc2026regmc")
    monkeypatch.setattr(
        SmogonSets, "get_random_spread", lambda _: PokemonSpread("bold", EVS, 1)
    )
    sampled, _ = get_battles_for_team_preview(loaded_battle(), 1)[0]
    sampled.team_preview = False
    state = battle_to_poke_engine_state(sampled)
    result = monte_carlo_tree_search(state, duration_ms=5)
    assert result.total_visits > 0
    assert result.side_two
    for action in result.side_two:
        for slot, decision in enumerate(action.move_choice):
            if decision.startswith("switch "):
                assert decision.removeprefix("switch ") in NAMES[2:]
            else:
                assert decision.split(",")[0] in MOVES[slot]


@pytest.mark.skipif(
    not os.environ.get("SHOWDOWN_SIM"), reason="Optional Showdown sheet contract"
)
def test_real_champions_open_sheet_matches_native_mcts_state(monkeypatch):
    monkeypatch.setattr(FoulPlayConfig, "pokemon_format", "gen9championsvgc2026regmc")
    script = Path(__file__).with_name("ots_reference.cjs")
    reference = json.loads(
        subprocess.check_output(
            ["node", str(script), os.environ["SHOWDOWN_SIM"]],
            text=True,
            timeout=20,
        )
    )
    packed = reference["line"].split("|", 3)[3]
    for raw in packed.split("]"):
        fields = raw.split("|")
        assert fields[6] == fields[8] == ""  # EVs and IVs really were hidden.
    b = Battle("battle-test")
    b.generation = "gen9"
    b.team_preview = True
    b.user.from_packed_string(packed)
    b.opponent.from_packed_string(packed)
    monkeypatch.setattr(
        SmogonSets, "get_random_spread", lambda _: PokemonSpread("bold", EVS, 1)
    )
    sampled, _ = get_battles_for_team_preview(b, 1)[0]
    state = battle_to_poke_engine_state(sampled)
    for native, expected in zip(state.side_two.pokemon, reference["expected"]):
        assert native.nature == normalize_name(expected["nature"])
        assert native.item == normalize_name(expected["item"])
        assert native.ability == normalize_name(expected["ability"])
        assert [m.id for m in native.moves] == [
            normalize_name(m) for m in expected["moves"]
        ]


@pytest.mark.parametrize(
    "mode, expected_spreads",
    [("gen9championsvgc2026regmcbo3", 2), ("gen9vgc2023regc", 1)],
)
def test_usage_spread_merging_respects_format_scale(
    monkeypatch, mode, expected_spreads
):
    sets = _SmogonSets()
    sets.pkmn_mode = mode
    raw = {
        "Froslass-Mega": {
            "Raw count": 100,
            "Teammates": {},
            "Checks and Counters": {},
            "Spreads": {
                "Timid:2/0/0/32/0/32": 60,
                "Timid:8/0/0/26/0/32": 25,  # exactly six: merge
                "Timid:9/0/0/25/0/32": 15,  # seven: retain in Champions
            },
        }
    }
    monkeypatch.setattr(sets, "_get_smogon_stats_json", lambda url: raw)
    spreads = sets._get_pokemon_information("unused", {"froslassmega"})["froslassmega"][
        "spreads"
    ]
    assert len(spreads) == expected_spreads
    assert spreads[0][0:2] == ["timid", "2,0,0,32,0,32"]
    if expected_spreads == 2:
        assert spreads[0][2] == pytest.approx(0.85)
        assert spreads[1] == ["timid", "9,0,0,25,0,32", 0.15]
    else:
        assert spreads[0][2] == pytest.approx(1.0)
