from types import SimpleNamespace

import pytest

from fp.search.helpers import format_decision


def slot(can_mega=True):
    return SimpleNamespace(
        active=SimpleNamespace(
            can_mega_evo=can_mega,
            can_ultra_burst=False,
            volatile_statuses=set(),
            terastallized=False,
            moves=[None, None],
        )
    )


@pytest.mark.parametrize(
    "decision,expected",
    [
        ("zapcannon,2,a,mega", "move zapcannon 1 mega"),
        ("zapcannon,2,b,mega", "move zapcannon 2 mega"),
        ("pollenpuff,1,a,mega", "move pollenpuff -1 mega"),
        ("pollenpuff,1,b,mega", "move pollenpuff -2 mega"),
        ("makeitrain,mega", "move makeitrain mega"),
        ("protect,mega", "move protect mega"),
        ("zapcannon,2,a", "move zapcannon 1"),
        ("protect", "move protect"),
        ("makeitrain", "move makeitrain"),
        ("zapcannon,2,a,tera", "move zapcannon 1 terastallize"),
        ("makeitrain,tera", "move makeitrain terastallize"),
        ("No Move", "pass"),
    ],
)
def test_move_targets_and_explicit_transformations(decision, expected):
    assert format_decision(SimpleNamespace(), slot(), decision) == expected


def test_reported_joint_choice_keeps_zap_cannon_target():
    battle = SimpleNamespace()
    choices = ("headsmash,2,a", "zapcannon,2,a,mega")
    commands = [format_decision(battle, slot(), c) for c in choices]
    assert (
        "/choose " + ",".join(commands)
        == "/choose move headsmash 1,move zapcannon 1 mega"
    )


@pytest.mark.parametrize("choice", ["zapcannon,2", "zapcannon,2,a,mega,tera"])
def test_malformed_choices_fail_explicitly(choice):
    with pytest.raises(ValueError, match="Malformed"):
        format_decision(SimpleNamespace(), slot(), choice)


def test_switch_indices_are_preserved():
    battle = SimpleNamespace(
        user=SimpleNamespace(reserve=[SimpleNamespace(name="arcanine", index=3)])
    )
    assert format_decision(battle, slot(), "switch arcanine") == "switch 3"
