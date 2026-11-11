import pytest
from poke_engine import State, monte_carlo_tree_search

from config import CustomFormatter, FoulPlayConfig
from fp.battle import Battle, Pokemon
from fp.battle_modifier import mega
from fp.search.poke_engine_helpers import (
    battle_to_poke_engine_state,
    pokemon_to_poke_engine_pkmn,
)


def pokemon(name, item=None):
    p = Pokemon(name, 50)
    p.ability = "none"
    p.item = item
    p.add_move("tackle")
    return p


def battle():
    b = Battle("battle-test")
    b.generation = "gen9"
    b.user.name = "p1"
    b.opponent.name = "p2"
    for side in (b.user, b.opponent):
        side.slot_a.active = pokemon("ampharos", "ampharosite")
        side.slot_b.active = pokemon("gholdengo")
        side.reserve = [pokemon("charizard", "charizarditex"), pokemon("pikachu")]
    return b


@pytest.mark.parametrize(
    "location", ["active_a", "active_b", "reserve", "fainted_reserve"]
)
@pytest.mark.parametrize("used_side", ["user", "opponent"])
def test_used_mega_blocks_further_mega_actions_after_serialization(
    location, used_side, monkeypatch
):
    monkeypatch.setattr(FoulPlayConfig, "pokemon_format", "gen9championsvgc2026regmc")
    b = battle()
    side = getattr(b, used_side)
    if location == "active_a":
        used = side.slot_a.active
    elif location == "active_b":
        used = side.slot_b.active
    else:
        used = side.reserve[0]
    used.is_mega = True
    if location == "fainted_reserve":
        used.hp = 0
    state = State.from_string(battle_to_poke_engine_state(b).to_string())
    # Exercise the actual compiled engine, including its root option generation.
    result = monte_carlo_tree_search(state, duration_ms=1)
    blocked = result.side_one if used_side == "user" else result.side_two
    available = result.side_two if used_side == "user" else result.side_one
    assert blocked
    assert not any(",mega" in move for action in blocked for move in action.move_choice)
    assert any(",mega" in move for action in available for move in action.move_choice)


def test_protocol_mega_event_reaches_engine_state():
    b = battle()
    mega(b, ["", "-mega", "p1a: Ampharos", "Ampharos", "Ampharosite"])
    assert b.user.slot_a.active.is_mega
    assert pokemon_to_poke_engine_pkmn(b.user.slot_a.active).mega_evolved


def test_no_mega_event_does_not_consume_the_resource():
    assert not pokemon_to_poke_engine_pkmn(
        pokemon("ampharos", "ampharosite")
    ).mega_evolved


def test_custom_formatter_interpolates_logging_arguments():
    import logging

    record = logging.LogRecord(
        "test",
        logging.ERROR,
        "",
        0,
        "Showdown rejected request %s: %s",
        (12, "invalid choice"),
        None,
    )
    text = CustomFormatter().format(record)
    assert "Showdown rejected request 12: invalid choice" in text
    assert "%s" not in text
