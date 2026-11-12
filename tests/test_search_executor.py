import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from poke_engine import Move, Pokemon, Side, SideSlot, State, TeamPreviewFilters

from fp.search.executor import get_search_executor, shutdown_search_executor
from fp.search.main import get_result_from_mcts, get_result_from_teampreview_mcts


@pytest.fixture(autouse=True)
def close_workers():
    shutdown_search_executor()
    yield
    shutdown_search_executor()


def search_state():
    def side():
        return Side(
            pokemon=[
                Pokemon(id=name, moves=[Move(id="tackle"), Move(id="protect")])
                for name in (
                    "pikachu",
                    "eevee",
                    "snorlax",
                    "gengar",
                    "arcanine",
                    "dragonite",
                )
            ],
            slot_a=SideSlot(active_index="0"),
            slot_b=SideSlot(active_index="1"),
        )

    return State(side_one=side(), side_two=side())


def test_spawned_worker_reused_across_preview_and_battle_searches():
    # The real application requests workers from an asyncio executor thread.
    with ThreadPoolExecutor(max_workers=1) as dispatch:
        pool = dispatch.submit(get_search_executor, 1).result(timeout=20)
    pid = pool.submit(os.getpid).result(timeout=20)
    assert pid != os.getpid()

    state = search_state()
    state.team_preview = True
    filters = TeamPreviewFilters(side_one=[(0, 1, 2, 3)], side_two=[(0, 1, 2, 3)])
    preview = pool.submit(
        get_result_from_teampreview_mcts, state.to_string(), 5, 0, filters
    ).result(timeout=20)
    assert preview.total_visits > 0
    assert len(preview.side_one) == 1

    state.team_preview = False
    # Different input states must work in the same process without retained tree
    # state from a previous game or preview search.
    state.side_one.pokemon[0].hp = 40
    result = (
        get_search_executor(1)
        .submit(get_result_from_mcts, state.to_string(), 5, 1)
        .result(timeout=20)
    )
    assert result.total_visits > 0
    assert result.side_one
    assert pool.submit(os.getpid).result(timeout=20) == pid

    shutdown_search_executor()
    new_pid = get_search_executor(1).submit(os.getpid).result(timeout=20)
    assert new_pid != pid


def test_invalid_parallelism_fails_before_starting_workers():
    with pytest.raises(ValueError, match="at least one"):
        get_search_executor(0)
