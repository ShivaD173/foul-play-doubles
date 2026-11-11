import asyncio
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import AsyncMock

import pytest
from poke_engine import generate_instructions

from config import FoulPlayConfig
from data.pkmn_sets import _SmogonSets
from fp.battle import Battle, Pokemon
from fp.helpers import normalize_name
from fp.search.poke_engine_helpers import battle_to_poke_engine_state
from teams.team_converter import export_to_dict, packed_to_dict

NAMES = ["raichu", "gholdengo", "arcanine", "garchomp", "dragonite", "rillaboom"]
EXPORT = """Sparky (Raichu) @ Raichunite Y
Ability: Lightning Rod
Level: 50
EVs: 32 SpA / 32 Spe
Timid Nature
- Fake Out
- Focus Blast
- Zap Cannon
- Protect

Gholdengo @ Life Orb
Ability: Good as Gold
Level: 50
EVs: 32 SpA / 32 Spe
Modest Nature
- Make It Rain
- Shadow Ball
- Nasty Plot
- Protect

Arcanine
Careful Nature
- Protect

Garchomp
Jolly Nature
- Protect

Dragonite
Adamant Nature
- Protect

Rillaboom
Adamant Nature
- Protect"""


def request():
    team = []
    for i, name in enumerate(NAMES):
        moves = (
            ["fakeout", "focusblast", "zapcannon", "protect"] if i == 0 else ["protect"]
        )
        stats = (
            {"atk": 99, "def": 75, "spa": 142, "spd": 100, "spe": 178}
            if i == 0
            else dict.fromkeys(["atk", "def", "spa", "spd", "spe"], 100)
        )
        ability = "lightningrod" if i == 0 else "none"
        team.append(
            dict(
                ident=f'p1: {"Sparky" if i == 0 else name}',
                details=f"{name}, L50",
                condition="135/135" if i == 0 else "100/100",
                active=i < 2,
                moves=moves,
                stats=stats,
                ability=ability,
                baseAbility=ability,
                item="raichunitey" if i == 0 else "",
            )
        )
    return dict(rqid=1, teamPreview=True, side=dict(id="p1", pokemon=team))


def live_battle(req=None):
    b = Battle("battle-test")
    b.generation = "gen9"
    b.user.initialize_first_turn_user_from_json(req or request())
    for slot, name in [
        (b.opponent.slot_a, "arcanine"),
        (b.opponent.slot_b, "gholdengo"),
    ]:
        slot.active = Pokemon(name, 50)
        slot.active.ability = "none"
        slot.active.item = None
        slot.active.add_move("protect")
    return b


def test_known_build_metadata_keeps_live_request_authoritative():
    b = live_battle()
    raichu = b.user.slot_a.active
    before = (
        raichu.hp,
        raichu.max_hp,
        dict(raichu.stats),
        raichu.item,
        raichu.ability,
        [(m.name, m.current_pp) for m in raichu.moves],
    )
    data = export_to_dict(EXPORT)
    data[0]["item"] = (
        "raichunitex"  # A stale export must not override the request's item.
    )
    data[0]["moves"] = ["tackle"]
    data[0]["ability"] = "static"
    b.user.apply_own_team_data(data)
    assert raichu.known_nature == raichu.nature == "timid"
    assert raichu.evs == (0, 0, 0, 32, 0, 32)
    after = (
        raichu.hp,
        raichu.max_hp,
        dict(raichu.stats),
        raichu.item,
        raichu.ability,
        [(m.name, m.current_pp) for m in raichu.moves],
    )
    assert before == after
    assert b.user.slot_b.active.nature == "modest"


@pytest.mark.parametrize(
    "item,expected,ability,spa,speed",
    [
        ("raichunitey", "raichumegay", "noguard", 212, 200),
        ("raichunitex", "raichumegax", "electricsurge", 142, 178),
    ],
)
def test_native_mega_uses_actual_stone_and_known_nature_and_points(
    item, expected, ability, spa, speed, monkeypatch
):
    monkeypatch.setattr(FoulPlayConfig, "pokemon_format", "gen9championsvgc2026regmc")
    b = live_battle()
    b.user.slot_a.active.item = item
    b.user.apply_own_team_data(export_to_dict(EXPORT))
    state = battle_to_poke_engine_state(b)
    assert state.side_one.pokemon[0].item == item
    assert state.side_one.pokemon[0].nature == "timid"
    assert state.side_one.pokemon[0].evs == (0, 0, 0, 32, 0, 32)
    # protect is slot 4 in the actual request, not the first move in a guessed set.
    results = generate_instructions(state, "protect,mega", "none", "none", "none")
    for result in results:
        raichu = state.apply_instructions(result).side_one.pokemon[0]
        assert normalize_name(raichu.id) == expected
        assert normalize_name(raichu.ability) == ability
        assert raichu.special_attack == spa
        assert raichu.speed == speed


@pytest.mark.parametrize(
    "item,expected",
    [
        ("raichunitey", {"raichu", "raichumegay"}),
        ("raichunitex", {"raichu", "raichumegax"}),
        (None, {"raichu"}),
        ("unknownitem", {"raichu", "raichumegax", "raichumegay"}),
    ],
)
def test_usage_lookup_includes_only_compatible_mega_forms(item, expected):
    p = Pokemon("raichu", 50)
    p.item = item
    assert _SmogonSets._lookup_names_for_pokemon(p) == expected


def test_disallowed_mega_is_not_reintroduced_by_alias_expansion(monkeypatch):
    manager = _SmogonSets()
    raw = dict.fromkeys(
        ["Raichu", "Raichu-Mega-X", "Raichu-Mega-Y"],
        {
            "Raw count": 100,
            "Teammates": {},
            "Checks and Counters": {},
            "Spreads": {"Timid:0/0/0/32/0/32": 100},
        },
    )
    monkeypatch.setattr(manager, "_get_smogon_stats_json", lambda _: raw)
    result = manager._get_pokemon_information("unused", {"raichu", "raichumegay"})
    assert set(result) == {"raichu", "raichumegay"}


def test_own_build_metadata_is_applied_before_team_preview(monkeypatch):
    import fp.run_battle as runner

    b = Battle("battle-test")
    b.user.name, b.opponent.name = "p1", "p2"
    packed = "Raichu||RaichuniteY|LightningRod|FakeOut,FocusBlast,ZapCannon,Protect|Timid|||||50|"
    # The test's own team has six species, as in a real initial request.
    # Omit own showteam here so that the complete export is the metadata source.
    msg = ">battle-test\n|clearpoke|\n|showteam|p2|" + packed
    monkeypatch.setattr(runner, "start_battle_common", AsyncMock(return_value=(b, msg)))

    async def first_request(client, battle):
        battle.user.initialize_first_turn_user_from_json(request())

    monkeypatch.setattr(runner, "get_first_request_json", first_request)
    monkeypatch.setattr(runner.SmogonSets, "load_speed_ranges", lambda _: None)
    preview = AsyncMock()
    monkeypatch.setattr(runner, "handle_team_preview", preview)
    result = asyncio.run(
        runner.start_standard_battle(
            object(),
            "gen9championsvgc2026regmc",
            False,
            [],
            team_dict=export_to_dict(EXPORT),
        )
    )
    raichu = next(p for p in result.user.reserve if p.name == "raichu")
    assert raichu.nature == "timid"
    assert raichu.evs == (0, 0, 0, 32, 0, 32)
    assert raichu.item == "raichunitey"
    preview.assert_awaited_once()


@pytest.mark.skipif(
    not os.environ.get("SHOWDOWN_SIM"), reason="Optional own-team reference"
)
def test_own_mega_y_stats_match_champions_reference(monkeypatch):
    monkeypatch.setattr(FoulPlayConfig, "pokemon_format", "gen9championsvgc2026regmc")
    script = Path(__file__).with_name("own_team_reference.cjs")
    ref = json.loads(
        subprocess.check_output(
            ["node", str(script), os.environ["SHOWDOWN_SIM"]], text=True, timeout=20
        )
    )
    b = live_battle(ref["request"])
    b.user.apply_own_team_data(export_to_dict(EXPORT))
    # The server's sheet can supply nature without erasing known investment.
    b.user.apply_own_team_data(packed_to_dict(ref["ownSheet"].split("|", 3)[3]))
    state = battle_to_poke_engine_state(b)
    results = generate_instructions(state, "protect,mega", "none", "none", "none")
    for result in results:
        own = state.apply_instructions(result).side_one.pokemon[0]
        assert normalize_name(own.id) == ref["mega"]["id"] == "raichumegay"
        assert normalize_name(own.ability) == ref["mega"]["ability"]
        assert [
            own.attack,
            own.defense,
            own.special_attack,
            own.special_defense,
            own.speed,
        ] == [ref["mega"]["stats"][key] for key in ["atk", "def", "spa", "spd", "spe"]]


def test_cached_lookup_names_refresh_when_own_mega_stone_changes(monkeypatch):
    from types import SimpleNamespace

    manager = _SmogonSets()
    own = Pokemon("raichu", 50)
    own.item = "raichunitey"

    def empty(reserve):
        return SimpleNamespace(
            reserve=reserve,
            slot_a=SimpleNamespace(active=None),
            slot_b=SimpleNamespace(active=None),
        )

    b = SimpleNamespace(user=empty([own]), opponent=empty([]))
    requested = []

    def fetch(url, names):
        requested.append(set(names))
        return dict.fromkeys(names, {})

    monkeypatch.setattr(manager, "_get_smogon_stats_file_name", lambda _: "same-url")
    monkeypatch.setattr(manager, "_get_pokemon_information", fetch)
    monkeypatch.setattr(manager, "_initialize", lambda *args: None)
    manager.initialize("gen9championsvgc2026regmc", b)
    own.item = "raichunitex"
    manager.initialize("gen9championsvgc2026regmc", b)
    assert requested == [{"raichu", "raichumegay"}, {"raichu", "raichumegax"}]
    assert "raichumegay" not in manager.raw_pkmn_sets


def test_two_known_stones_on_opposing_teams_can_legitimately_cache_both(monkeypatch):
    from types import SimpleNamespace

    manager = _SmogonSets()
    own, opponent = Pokemon("raichu", 50), Pokemon("raichu", 50)
    own.item, opponent.item = "raichunitey", "raichunitex"

    def side(p):
        return SimpleNamespace(
            reserve=[p],
            slot_a=SimpleNamespace(active=None),
            slot_b=SimpleNamespace(active=None),
        )

    b = SimpleNamespace(user=side(own), opponent=side(opponent))
    requested = []

    def fetch(url, names):
        requested.append(set(names))
        return dict.fromkeys(names, {})

    monkeypatch.setattr(manager, "_get_smogon_stats_file_name", lambda _: "same-url")
    monkeypatch.setattr(manager, "_get_pokemon_information", fetch)
    monkeypatch.setattr(manager, "_initialize", lambda *args: None)
    manager.initialize("gen9championsvgc2026regmc", b)
    assert requested == [{"raichu", "raichumegax", "raichumegay"}]
