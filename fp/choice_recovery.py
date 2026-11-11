"""Bounded recovery from rejected Showdown choices."""

import logging

logger = logging.getLogger(__name__)


class ChoiceRecovery:
    def __init__(self):
        self.fallback_rqid = None

    async def recover(self, client, battle, message):
        lines = message.splitlines()
        if not lines or lines[0] != ">" + battle.battle_tag:
            return False
        errors = [
            line
            for line in lines[1:]
            if line.startswith(
                ("|error|[Invalid choice]", "|error|[Unavailable choice]")
            )
        ]
        if not errors or battle.wait or battle.rqid is None:
            return False
        reason = "\n".join(errors)
        if self.fallback_rqid == battle.rqid:
            raise RuntimeError(
                "Showdown rejected automatic choice for request {}: {}".format(
                    battle.rqid, reason
                )
            )
        logger.error(
            "Showdown rejected request %s: %s. Sending /choose default once.",
            battle.rqid,
            reason,
        )
        # Let Showdown choose a legal complete action, including targets and
        # forced switches. This is emergency recovery, not the normal policy.
        self.fallback_rqid = battle.rqid
        await client.send_message(
            battle.battle_tag, ["/choose default", str(battle.rqid)]
        )
        # The rejected MCTS choices are no longer evidence for speed inference.
        for slot in (battle.user.slot_a, battle.user.slot_b):
            slot.last_selected_move = slot.last_selected_move._replace(
                move="none", turn=-1
            )
        return True
