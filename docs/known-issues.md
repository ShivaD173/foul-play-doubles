# Remaining Champions issues and integration work

Target: **[Gen 9 Champions] VGC 2026 Reg M-C**, ID
`gen9championsvgc2026regmc`, Showdown mod `champions`.

## Engine mechanics

The canonical inventory is in the sibling engine repository:

**[Remaining Champions issues](https://github.com/ShivaD173/poke-engine-doubles/blob/main/docs/remaining-issues.md)**

It retains the original review IDs, reproduction/source-review distinctions,
Champions availability corrections, lower-priority incomplete mechanics, and
unchanged search approximations. It also identifies the selected fixes
(2, 3, 7, 11, 19) and their related resolved findings. The read-only Showdown
reference and test instructions are in the
[engine audit](https://github.com/ShivaD173/poke-engine-doubles/blob/main/docs/champions-spread-audit.md).

In particular, Make It Rain's **95% accuracy and -2 SpA drop are correct for
Champions**. The earlier review used the wrong format for that finding.

## Unfixed client issues

These are source findings/integration limitations, not claims of completed
end-to-end tests against a live Champions server.

### Published engine dependency does not include the local fixes

[requirements.txt](../requirements.txt) installs `poke-engine-doubles==0.0.7`
from PyPI with the `terastallization` feature. Merely pushing changes to the
engine fork does not change that package. Champions needs Mega Evolution
support, and the patched engine must be installed explicitly. With both
repositories checked out beside each other, activate this client's virtual
environment and run from the client repository:

```sh
pip install --force-reinstall --no-cache-dir ../poke-engine-doubles/poke-engine-py \
  --config-settings="build-args=--features poke-engine/mega --no-default-features"
```

Reinstalling the existing requirements afterward replaces this build. A durable
deployment still needs a pinned engine commit/build or a released patched
package and corresponding dependency changes.

### Accuracy/evasion stages are discarded (original finding 20)

[fp/search/poke_engine_helpers.py](../fp/search/poke_engine_helpers.py) serializes
`accuracy_boost=0` and `evasion_boost=0`. The engine also has a separate target-
evasion calculation issue. Both sides need attention for faithful predictions.

### Startup assumes particular websocket frame boundaries

[fp/run_battle.py](../fp/run_battle.py) consumes the initial room message, then
waits separately for player/request messages. `get_first_request_json` tests the
first pipe-delimited event instead of processing every event in a frame. A
request bundled with initialization can be skipped. Startup also expects the
opponent's `showteam` event in a particular preview frame and indexes it without
handling absence. Preserve/process all events and retain requests/team sheets
across frames when addressing this.

### The client assumes a best-of-three room

[run.py](../run.py) calls `_get_best_of_3_room_name` and uses a best-of-three
loop. This is not a general single-game startup path. Confirm the intended
challenge/server behavior before treating the non-Bo3 format as turnkey.

### Engine reinstall Make target references a missing configuration file

The `poke_engine` target in [Makefile](../Makefile) reads the package version
from `pyproject.toml`, but that file is absent in this client checkout. The
explicit sibling-source installation command above avoids that target; the
target itself remains unfixed.

## Search timing and benchmark limits

- Battle search samples **four opponent states**. `--search-time-ms` is a budget
  for each sampled state. With one process, four 10-second searches require
  roughly 40 seconds plus overhead; multiple processes compete for CPU/memory.
- The current client calls the engine without passing a thread count. Process
  parallelism across samples and shared-tree engine threading are different.
- Measured engine cleanup can extend a 10-second search-budget call to roughly
  11–14 seconds on larger positions. This is not a hard turn-time guarantee.
- Single-threaded and shared-tree searches have different depth limits (4 and
  6 completed turns respectively), so raw iteration counts are not a pure
  multithreading speedup comparison. The engine caps a tree at 25 million
  iterations.

No heuristic implementation from the earlier singles-repository experiment was
copied into this doubles client. This client continues to use doubles MCTS.

## Resolved preview API incompatibility

The engine exposes `TeamPreviewFilters(side_one=[...], side_two=[...])` with
zero-based four-Pokemon index options. It does **not** export
`TeamPreviewFilterSide`. The client previously imported an obsolete engine API
and failed at startup with that ImportError. It now keeps its named constraints
in `fp/search/team_preview.py` and converts them to the engine's indexed API.
Historical unordered lead pairs allow both slot orders, while equivalent backup
orders are not duplicated. Filters remain serializable for process workers.

Preview parallelism is also clamped to at least one sample/worker, so a configured
`--search-parallelism 1` no longer produces a zero-worker preview search. This
does not alter the four-state sampling policy for battle decisions.

## Resolved Mega choice formatting and rejected-choice handling

The client previously removed `,tera` before parsing targets but did not remove
`,mega`. An engine decision such as `zapcannon,2,a,mega` therefore bypassed the
three-field target parser and became `move zapcannon mega`, which Showdown
rejects in doubles. Mega eligibility also caused the client to add `mega` to
plain move choices even when MCTS had not selected the transformation.

The formatter now parses the explicit transformation first, preserves the
signed target, and honors MCTS's Mega decision. The reported joint action is
sent as `/choose move headsmash 1,move zapcannon 1 mega`.

During the battle loop, an `[Invalid choice]` or `[Unavailable choice]` error
from the current room now triggers one `/choose default` response for the
current request. Showdown supplies a legal complete action, including required
targets and switches. This emergency action can differ from the searched policy;
normal turns continue to use MCTS. The rejected move is cleared from selected-
move inference. If automatic recovery is also rejected for the same request,
the client raises an explicit error instead of repeatedly retrying or silently
waiting for a timeout. This recovery does not redesign startup/preview handling.

`tests/test_format_decision.py` includes the exact reported action and checks
both ally/foe targets, spread/self moves, explicit Mega/Tera choices, and plain
moves with Mega eligibility. `tests/test_choice_recovery.py` exercises bounded
recovery and the battle loop without requiring a new request after rejection.
For an optional read-only check against a compiled Showdown reference:

```sh
node tests/choice_reference.cjs /absolute/path/to/showdown/dist/sim
```

## Resolved Mega resource serialization

The client tracked protocol Mega Evolution events as `Pokemon.is_mega`, but the
state adapter omitted the engine's `mega_evolved` constructor argument. Every
serialized Pokemon therefore defaulted to `mega_evolved=False`, allowing MCTS
to offer another Mega Evolution after a teammate had already used it.

The adapter now exports the flag for both sides, including reserves and fainted
Pokemon. The existing engine already scans the side's entire team for a used
Mega; no engine/binding rebuild is required for this client fix. Compiled-engine
regressions verify root actions after state serialization with the flag in
either active slot, in reserve, and on a fainted reserve, independently for
both sides. Protocol-event-to-engine serialization is tested as well.

As a defensive boundary check, the formatter only sends a requested Mega flag
when the latest Showdown request allows the active Pokemon to Mega Evolve.
If not, it logs a warning and retains the searched move and target without the
Mega flag. The primary fix is to model the spent resource correctly in search,
not merely rely on emergency `/choose default` recovery.

The custom log formatter now calls `LogRecord.getMessage()` so parameterized
messages show actual request IDs and error details rather than literal `%s`.
