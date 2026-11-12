"""Compare fresh and reused workers using four short native MCTS searches."""

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poke_engine import Move, Pokemon, Side, SideSlot, State  # noqa: E402

from fp.search.executor import get_search_executor, shutdown_search_executor  # noqa: E402
from fp.search.main import get_result_from_mcts  # noqa: E402


def state_string():
    def side():
        return Side(
            pokemon=[
                Pokemon(
                    id=name,
                    hp=180,
                    maxhp=180,
                    moves=[
                        Move(id=m)
                        for m in ("tackle", "protect", "shadowball", "thunderbolt")
                    ],
                )
                for name in ("gholdengo", "raichu", "arcanine", "garchomp")
            ],
            slot_a=SideSlot(active_index="0"),
            slot_b=SideSlot(active_index="1"),
        )

    return State(side_one=side(), side_two=side()).to_string()


def main():
    state = state_string()
    for mode in ("fresh", "reused"):
        for trial in range(4):
            started = time.perf_counter()
            pool = (
                ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn"))
                if mode == "fresh"
                else get_search_executor(2)
            )
            futures = [
                pool.submit(get_result_from_mcts, state, 50, i) for i in range(4)
            ]
            visits = sum(f.result().total_visits for f in futures)
            if mode == "fresh":
                pool.shutdown()
            print(
                f"DISPATCH mode={mode} trial={trial} seconds={time.perf_counter() - started:.6f} visits={visits}",
                flush=True,
            )
        shutdown_search_executor()


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown_search_executor()
