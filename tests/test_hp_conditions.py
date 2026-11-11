import json
import os
from pathlib import Path
import subprocess

import pytest

from fp.battle import Battle, Pokemon
from fp.battle_modifier import get_damage_dealt
from fp.helpers import get_pokemon_info_from_condition


@pytest.mark.parametrize(
    "hp,maxhp,color",
    [
        (50, 100, "y"),
        (50, 100, "g"),
        (20, 100, "r"),
        (20, 100, "y"),
        (24, 48, "g"),
        (24, 48, "y"),
        (9, 48, "r"),
        (9, 48, "y"),
        (181, 181, ""),
    ],
)
@pytest.mark.parametrize("status", [None, "brn", "par", "slp", "psn", "tox", "frz"])
def test_hp_condition_accepts_color_and_preserves_status(hp, maxhp, color, status):
    condition = f"{hp}/{maxhp}{color}" + (f" {status}" if status else "")
    assert get_pokemon_info_from_condition(condition) == (hp, maxhp, status)


@pytest.mark.parametrize("condition", ["0 fnt", "0/100 fnt", "0/100y fnt"])
def test_fainted_conditions_keep_existing_semantics(condition):
    assert get_pokemon_info_from_condition(condition) == (0, 0, None)


@pytest.mark.parametrize("condition", ["", "50/100garbage", "50/100yy", "50/100 xyz"])
def test_invalid_conditions_are_not_silently_accepted(condition):
    with pytest.raises(ValueError):
        get_pokemon_info_from_condition(condition)


def test_spread_damage_inference_accepts_champions_hp_color():
    b = Battle("battle-test")
    b.user.name, b.opponent.name = "p1", "p2"
    b.user.slot_a.active = Pokemon("raichu", 50)
    b.user.slot_b.active = Pokemon("gholdengo", 50)
    b.opponent.slot_a.active = Pokemon("pawmot", 50)
    b.opponent.slot_b.active = Pokemon("rillaboom", 50)
    for p in [b.opponent.slot_a.active, b.opponent.slot_b.active]:
        p.hp = p.max_hp = 100
    move = "|move|p1b: Gholdengo|Make It Rain|p2a: Pawmot|[spread] p2a,p2b"
    damage = get_damage_dealt(
        b,
        move.split("|"),
        [
            "|-damage|p2a: Pawmot|1/100",
            "|-damage|p2b: Rillaboom|50/100y",
        ],
    )
    assert len(damage) == 2
    assert [d.percent_damage for d in damage] == [0.99, 0.5]
    assert all(d.spread for d in damage)


@pytest.mark.skipif(
    not os.environ.get("SHOWDOWN_SIM"), reason="Optional read-only Showdown reference"
)
def test_real_champions_hp_strings_parse():
    script = Path(__file__).with_name("hp_reference.cjs")
    cases = json.loads(
        subprocess.check_output(
            ["node", str(script), os.environ["SHOWDOWN_SIM"]],
            text=True,
            timeout=20,
        )
    )
    assert len(cases) == 28
    for case in cases:
        assert get_pokemon_info_from_condition(case["condition"]) == tuple(
            case["expected"]
        )
