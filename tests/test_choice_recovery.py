import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fp.battle import LastUsedMove
from fp.choice_recovery import ChoiceRecovery


def battle():
    def slot():
        return SimpleNamespace(
            last_selected_move=LastUsedMove("ampharos", "zapcannon", 4)
        )

    return SimpleNamespace(
        battle_tag="battle-test",
        rqid=12,
        wait=False,
        user=SimpleNamespace(slot_a=slot(), slot_b=slot()),
    )


ERROR = ">battle-test\n|error|[Invalid choice] Can't move: Zap Cannon needs a target"


def test_invalid_choice_gets_one_server_generated_legal_choice():
    b = battle()
    client = SimpleNamespace(send_message=AsyncMock())
    recovery = ChoiceRecovery()
    assert asyncio.run(recovery.recover(client, b, ERROR))
    client.send_message.assert_awaited_once_with(
        "battle-test", ["/choose default", "12"]
    )
    assert b.user.slot_a.last_selected_move.turn == -1
    assert b.user.slot_b.last_selected_move.move == "none"
    with pytest.raises(RuntimeError, match="rejected automatic choice"):
        asyncio.run(recovery.recover(client, b, ERROR))
    assert client.send_message.await_count == 1
    b.rqid = 13
    assert asyncio.run(recovery.recover(client, b, ERROR))
    assert client.send_message.await_count == 2


@pytest.mark.parametrize(
    "message",
    [
        ">battle-other\n|error|[Invalid choice] bad target",
        ">battle-test\n|error|Access denied",
        ">battle-test\n|inactive|Time left: 55 sec",
    ],
)
def test_unrelated_messages_do_not_submit_choices(message):
    client = SimpleNamespace(send_message=AsyncMock())
    assert not asyncio.run(ChoiceRecovery().recover(client, battle(), message))
    client.send_message.assert_not_awaited()


def test_waiting_does_not_submit_another_choice():
    b = battle()
    b.wait = True
    client = SimpleNamespace(send_message=AsyncMock())
    assert not asyncio.run(ChoiceRecovery().recover(client, b, ERROR))
    client.send_message.assert_not_awaited()


def test_battle_loop_recovers_from_rejection_without_waiting_for_new_request(
    monkeypatch,
):
    import fp.run_battle as runner
    from config import FoulPlayConfig, SaveReplay
    from fp.battle import Battle

    b = Battle("battle-test")
    b.rqid = 12
    client = SimpleNamespace(
        receive_message=AsyncMock(side_effect=[ERROR, ">battle-test\n|win|Bot"]),
        send_message=AsyncMock(),
        leave_battle=AsyncMock(),
    )
    monkeypatch.setattr(runner, "start_battle", AsyncMock(return_value=b))
    pick = AsyncMock()
    monkeypatch.setattr(runner, "async_pick_move", pick)
    monkeypatch.setattr(runner.SmogonSets, "save_speed_ranges", lambda _: None)
    monkeypatch.setattr(FoulPlayConfig, "save_replay", SaveReplay.never, raising=False)
    monkeypatch.setattr(FoulPlayConfig, "username", "Bot", raising=False)
    result = asyncio.run(
        runner.pokemon_battle(
            client, "gen9championsvgc2026regmcbo3", "game-bestof3-test", True, []
        )
    )
    assert result[0] == "Bot"
    client.send_message.assert_any_await("battle-test", ["/choose default", "12"])
    client.leave_battle.assert_awaited_once_with("battle-test")
    pick.assert_not_awaited()
