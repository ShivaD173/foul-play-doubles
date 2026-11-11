import pickle
from types import SimpleNamespace

import pytest
from poke_engine import Move, Pokemon, Side, SideSlot, State

from fp.battle import BattleData
from fp.search.main import get_teampreview_filters, get_result_from_teampreview_mcts
from fp.search.team_preview import TeamPreviewFilterSide, team_preview_options

NAMES = ["pikachu", "eevee", "snorlax", "gengar", "arcanine", "dragonite"]


def preview_battle(history=None):
    return SimpleNamespace(
        user=SimpleNamespace(reserve=[SimpleNamespace(name=n) for n in NAMES]),
        opponent=SimpleNamespace(reserve=[SimpleNamespace(name=n) for n in NAMES]),
        previous_battle_data=history or [],
    )


def test_all_teams_have_unique_actions_and_four_distinct_indices():
    options = team_preview_options(NAMES, TeamPreviewFilterSide(NAMES))
    assert len(options) == 180
    actions = {(a, b, frozenset((c, d))) for a, b, c, d in options}
    assert len(actions) == 180
    assert all(len(set(o)) == 4 and all(0 <= i < 6 for i in o) for o in options)


def test_restricted_picks_and_unordered_historical_leads():
    options = team_preview_options(
        NAMES, TeamPreviewFilterSide(NAMES[:4], leads=[("eevee", "pikachu")])
    )
    assert options == [(0, 1, 2, 3), (1, 0, 2, 3)]


def test_indices_follow_serialized_team_order():
    names = list(reversed(NAMES))
    options = team_preview_options(
        names, TeamPreviewFilterSide(NAMES[:4], leads=[("eevee", "pikachu")])
    )
    assert {o[:2] for o in options} == {(4, 5), (5, 4)}
    assert all(set(names[i] for i in o) == set(NAMES[:4]) for o in options)


@pytest.mark.parametrize(
    "constraints",
    [
        TeamPreviewFilterSide(NAMES[:3]),
        TeamPreviewFilterSide(["unknown"]),
        TeamPreviewFilterSide(NAMES, leads=[]),
    ],
)
def test_invalid_constraints_do_not_reach_rust(constraints):
    with pytest.raises(ValueError):
        team_preview_options(NAMES, constraints)


def test_filter_constructor_and_pickle_work_with_compiled_engine():
    filters = get_teampreview_filters(preview_battle(), TeamPreviewFilterSide(NAMES), 2)
    assert len(filters) == 2
    for f in filters:
        restored = pickle.loads(pickle.dumps(f))
        assert len(restored.side_one) == len(restored.side_two) == 180


def test_history_restricts_opponents_team_and_both_lead_orders():
    history = [BattleData(set(NAMES[:2]), set(NAMES[2:4]), False)]
    filters = get_teampreview_filters(
        preview_battle(history), TeamPreviewFilterSide(NAMES), 2
    )
    assert len(filters) == 2
    assert all(f.side_two == [[0, 1, 2, 3], [1, 0, 2, 3]] for f in filters)


def test_incomplete_history_keeps_known_leads_but_allows_unknown_backups():
    history = [BattleData(set(NAMES[:2]), set(), True)]
    filters = get_teampreview_filters(
        preview_battle(history), TeamPreviewFilterSide(NAMES), 1
    )
    assert len(filters[0].side_two) == 12
    assert all(set(o[:2]) == {0, 1} for o in filters[0].side_two)


def test_real_team_preview_mcts_accepts_index_filters():
    battle = preview_battle()
    filters = get_teampreview_filters(
        battle, TeamPreviewFilterSide(NAMES[:4], [("pikachu", "eevee")]), 1
    )[0]
    # Keep the smoke test small while using the real compiled extension.
    from poke_engine import TeamPreviewFilters

    filters = TeamPreviewFilters(side_one=filters.side_one, side_two=[(0, 1, 2, 3)])

    def side():
        return Side(
            pokemon=[
                Pokemon(
                    id=n,
                    moves=[
                        Move(id="tackle"),
                        Move(id="protect"),
                        Move(id="none"),
                        Move(id="none"),
                    ],
                )
                for n in NAMES
            ],
            slot_a=SideSlot(active_index="0"),
            slot_b=SideSlot(active_index="1"),
        )

    state = State(side_one=side(), side_two=side(), team_preview=True)
    result = get_result_from_teampreview_mcts(state.to_string(), 5, 0, filters)
    assert result.total_visits > 0
    assert len(result.side_one) == 2
    assert {
        tuple(choice.move_choice[0].split(",")[:1]) for choice in result.side_one
    } == {("pikachu",), ("eevee",)}
