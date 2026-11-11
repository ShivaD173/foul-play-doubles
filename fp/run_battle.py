import json
import asyncio
import concurrent.futures
from copy import deepcopy
import logging

import constants
from config import FoulPlayConfig, SaveReplay
from data.pkmn_sets import SmogonSets
from fp.battle import LastUsedMove, Pokemon, Battle, BattleData
from fp.choice_recovery import ChoiceRecovery
from fp.search.helpers import format_decision
from fp.battle_modifier import async_update_battle
from fp.helpers import normalize_name
from fp.search.main import find_best_move, find_best_move_teampreview

from fp.websocket_client import PSWebsocketClient

logger = logging.getLogger(__name__)


def battle_is_finished(battle_tag, msg):
    return (
        msg.startswith(">{}".format(battle_tag))
        and (constants.WIN_STRING in msg or constants.TIE_STRING in msg)
        and constants.CHAT_STRING not in msg
    )


def bo3_is_finished(bo3_tag, msg):
    return (
        msg.startswith(">{}".format(bo3_tag))
        and (constants.WIN_STRING in msg or constants.TIE_STRING in msg)
        and constants.CHAT_STRING not in msg
    )


def extract_battle_factory_tier_from_msg(msg):
    start = msg.find("Battle Factory Tier: ") + len("Battle Factory Tier: ")
    end = msg.find("</b>", start)
    tier_name = msg[start:end]

    return normalize_name(tier_name)


async def async_pick_move_teampreview(battle):
    battle_copy = deepcopy(battle)
    if not battle_copy.team_preview:
        battle_copy.user.update_from_request_json(battle_copy.request_json)

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        choice_a, choice_b = await loop.run_in_executor(
            pool, find_best_move_teampreview, battle_copy
        )
    switch_a, faint_1 = choice_a.split(",")
    switch_b, faint_2 = choice_b.split(",")
    logger.info(f"Leads: {switch_a}, {switch_b}")
    logger.info(f"Leaving behind: {faint_1}, {faint_2}")

    return (switch_a, switch_b), (faint_1, faint_2)


async def async_pick_move(battle):
    battle_copy = deepcopy(battle)
    if not battle_copy.team_preview:
        battle_copy.user.update_from_request_json(battle_copy.request_json)

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        choice_a, choice_b = await loop.run_in_executor(
            pool, find_best_move, battle_copy
        )
    battle.user.slot_a.last_selected_move = LastUsedMove(
        battle.user.slot_a.active.name,
        choice_a.split(",")[0],
        battle.turn,
    )
    battle.user.slot_b.last_selected_move = LastUsedMove(
        battle.user.slot_b.active.name,
        choice_b.split(",")[0],
        battle.turn,
    )
    decision_a = format_decision(battle_copy, battle_copy.user.slot_a, choice_a)
    decision_b = format_decision(battle_copy, battle_copy.user.slot_b, choice_b)
    return decision_a, decision_b


async def handle_team_preview(battle, ps_websocket_client):
    battle_copy = deepcopy(battle)
    battle_copy.user.slot_a.active = Pokemon.get_dummy()
    battle_copy.user.slot_b.active = Pokemon.get_dummy()
    battle_copy.opponent.slot_a.active = Pokemon.get_dummy()
    battle_copy.opponent.slot_b.active = Pokemon.get_dummy()
    battle_copy.team_preview = True

    (switch_a, switch_b), (faint_1, faint_2) = await async_pick_move_teampreview(
        battle_copy
    )

    lead_indices = []
    take_in_reserve_indices = []
    for pkmn in battle.user.reserve:
        if pkmn.name in [faint_1, faint_2]:
            logger.info(f"Setting {pkmn.name} as fainted as it is not chosen")
            pkmn.hp = 0
            pkmn.name = "none"  # poke-engine uses none to identify pokemon that are not in the battle
        elif pkmn.name in [switch_a, switch_b]:
            logger.info(f"Choosing {pkmn.name} (index={pkmn.index}) as lead")
            lead_indices.append(pkmn.index)
        else:
            logger.info(f"Taking {pkmn.name} (index={pkmn.index}) as reserve")
            take_in_reserve_indices.append(pkmn.index)

    message = [
        "/team {}{}{}{}|{}".format(
            lead_indices[0],
            lead_indices[1],
            take_in_reserve_indices[0],
            take_in_reserve_indices[1],
            battle.rqid,
        )
    ]
    await ps_websocket_client.send_message(battle.battle_tag, message)


async def get_battle_tag_and_opponent(ps_websocket_client: PSWebsocketClient):
    while True:
        msg = await ps_websocket_client.receive_message()
        split_msg = msg.split("|")
        first_msg = split_msg[0]
        if "battle" in first_msg:
            battle_tag = first_msg.replace(">", "").strip()
            user_name = FoulPlayConfig.username
            opponent_name = (
                split_msg[4].replace(user_name, "").replace("vs.", "").strip()
            )
            return battle_tag, opponent_name


async def start_battle_common(
    ps_websocket_client: PSWebsocketClient, pokemon_battle_type
):
    battle_tag, opponent_name = await get_battle_tag_and_opponent(ps_websocket_client)
    if FoulPlayConfig.log_to_file:
        FoulPlayConfig.file_log_handler.do_rollover(
            "{}_{}.log".format(battle_tag, opponent_name)
        )

    battle = Battle(battle_tag)
    battle.opponent.account_name = opponent_name
    battle.generation = pokemon_battle_type[:4]

    # wait until the opponent's identifier is received. This will be `p1` or `p2`.
    #
    # e.g.
    # '>battle-gen9randombattle-44733
    # |player|p1|OpponentName|2|'
    while True:
        msg = await ps_websocket_client.receive_message()
        if "|player|" in msg and battle.opponent.account_name in msg:
            battle.opponent.name = msg.split("|")[2]
            battle.user.name = constants.ID_LOOKUP[battle.opponent.name]
            break

    return battle, msg


async def get_first_request_json(
    ps_websocket_client: PSWebsocketClient, battle: Battle
):
    while True:
        msg = await ps_websocket_client.receive_message()
        msg_split = msg.split("|")
        if msg_split[1].strip() == "request" and msg_split[2].strip():
            user_json = json.loads(msg_split[2].strip("'"))
            battle.request_json = user_json
            battle.user.initialize_first_turn_user_from_json(user_json)
            battle.rqid = user_json[constants.RQID]
            return


async def start_standard_battle(
    ps_websocket_client: PSWebsocketClient,
    pokemon_battle_type,
    first_battle,
    all_battle_data,
    team_dict=None,
):
    battle, msg = await start_battle_common(ps_websocket_client, pokemon_battle_type)
    battle.battle_type = constants.STANDARD_BATTLE
    battle.previous_battle_data = all_battle_data

    while constants.START_TEAM_PREVIEW not in msg:
        msg = await ps_websocket_client.receive_message()

    opponent_showteam = [
        line
        for line in msg.split("\n")
        if line.startswith(f"|showteam|{battle.opponent.name}")
    ][0].split("|", 3)[3]
    battle.opponent.from_packed_string(opponent_showteam)

    await get_first_request_json(ps_websocket_client, battle)
    battle.user.apply_own_team_data(team_dict)
    # The server's own sheet confirms the nature without replacing live stats.
    own_sheets = [
        line
        for line in msg.split("\n")
        if line.startswith(f"|showteam|{battle.user.name}|")
    ]
    if own_sheets:
        from teams.team_converter import packed_to_dict

        own_sheet = packed_to_dict(own_sheets[-1].split("|", 3)[3])
        battle.user.apply_own_team_data(own_sheet)
    battle.during_team_preview()

    if first_battle:
        SmogonSets.initialize(pokemon_battle_type, battle)

    SmogonSets.load_speed_ranges(battle)
    battle.user.reserve.insert(0, battle.user.slot_a.active)
    battle.user.reserve.insert(0, battle.user.slot_b.active)
    battle.user.slot_a.active = None
    battle.user.slot_b.active = None
    await handle_team_preview(battle, ps_websocket_client)
    return battle


async def start_battle(
    ps_websocket_client,
    pokemon_battle_type,
    first_battle,
    all_battle_data,
    team_dict=None,
):
    battle = await start_standard_battle(
        ps_websocket_client,
        pokemon_battle_type,
        first_battle,
        all_battle_data,
        team_dict=team_dict,
    )

    await ps_websocket_client.send_message(battle.battle_tag, ["/timer on"])

    return battle


async def pokemon_battle(
    ps_websocket_client,
    pokemon_battle_type,
    best_of_3_room_name,
    first_battle,
    all_battle_data: list[BattleData],
    team_dict=None,
):
    battle = await start_battle(
        ps_websocket_client,
        pokemon_battle_type,
        first_battle,
        all_battle_data,
        team_dict=team_dict,
    )
    choice_recovery = ChoiceRecovery()
    while True:
        msg = await ps_websocket_client.receive_message()
        if battle_is_finished(battle.battle_tag, msg):
            if constants.WIN_STRING in msg:
                winner = msg.split(constants.WIN_STRING)[-1].split("\n")[0].strip()
            else:
                winner = None
            logger.info("Winner: {}".format(winner))
            if FoulPlayConfig.save_replay == SaveReplay.always or (
                FoulPlayConfig.save_replay == SaveReplay.on_loss
                and winner != FoulPlayConfig.username
            ):
                await ps_websocket_client.save_replay(battle.battle_tag)
            await ps_websocket_client.leave_battle(battle.battle_tag)
            SmogonSets.save_speed_ranges(battle)
            return winner, False, battle.battle_data
        elif bo3_is_finished(best_of_3_room_name, msg):
            if constants.WIN_STRING in msg:
                winner = msg.split(constants.WIN_STRING)[-1].split("\n")[0].strip()
            else:
                winner = None
            logger.info("Bo3 Winner: {}".format(winner))
            if FoulPlayConfig.save_replay == SaveReplay.always or (
                FoulPlayConfig.save_replay == SaveReplay.on_loss
                and winner != FoulPlayConfig.username
            ):
                await ps_websocket_client.save_replay(battle.battle_tag)
            await ps_websocket_client.leave_battle(battle.battle_tag)
            return winner, True, battle.battle_data
        else:
            action_required = await async_update_battle(battle, msg)
            if await choice_recovery.recover(ps_websocket_client, battle, msg):
                continue
            if action_required and not battle.wait:
                best_move_a, best_move_b = await async_pick_move(battle)
                best_move = [f"/choose {best_move_a},{best_move_b}", str(battle.rqid)]
                await ps_websocket_client.send_message(battle.battle_tag, best_move)
