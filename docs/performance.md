# Search performance

Target: `[Gen 9 Champions] VGC 2026 Reg M-C` (`champions`).

## Changes

- Search processes stay alive between team preview, turns, and games. Both
  preview and regular searches use the same pool, capped by
  `--search-parallelism`. Preview still submits its original smaller number of
  samples. The pool uses `spawn`, including on Linux, because dispatch happens
  from a thread. This also exercises the macOS process-start path.
- The asyncio loop reuses its executor thread to dispatch decisions.
- Sampling no longer deep-copies the entire battle once before making the
  existing independent copy for each sample. The live battle remains untouched.
- Preview options, serialized input states, and iteration counts are logged by
  the parent process so logs follow the current battle's file.

Workers remain resident while the bot runs. They do not retain a search tree
between jobs, although their allocator can retain freed memory. The command-line
entry point shuts down the pool on exit; library callers can use
`fp.search.executor.shutdown_search_executor()` when finished. Changing the
configured worker count replaces the pool. The first call still pays process
startup costs.

The engine now uses mimalloc for Rust allocations in its Python extension and
CLI. In the Linux benchmarks, median iterations completed within ten seconds
increased from 1.100 million to 1.359 million in the opening fixture (+23.5%),
and from 325,000 to 382,000 in the chance-heavy fixture (+17.5%). Larger trees
also increased measured peak memory by about 19%. Fixed-seed comparisons
preserved the exact policy scores and visit counts. These are synthetic,
single-thread measurements; local hardware and positions can differ.

The engine also caches chance distributions and makes full-tree diagnostic
printing opt-in. See the engine's
[benchmark and results](https://github.com/ShivaD173/poke-engine-doubles/blob/main/docs/performance.md).
Rebuild its Python extension to receive those changes:

```sh
# In foul-play-doubles, with your virtualenv activated and the engine beside it:
make poke_engine_local GEN=mega
```

## Worker dispatch measurement

These dispatch measurements predate the allocator change and measure a separate
source of overhead; they are not used for the iteration-throughput figures above.

On Linux/Python 3.12 with a two-CPU quota, four 50 ms native searches on two
spawned workers took a median **266 ms** with fresh workers versus **120 ms**
with reused workers. These medians exclude the first trial in both modes;
first-trial times were 308 ms and 230 ms. This test used the pre-optimization
native extension in both modes, isolating worker reuse. It used a synthetic
state, not a legal team or a battle replay. Results on macOS can differ.

This is about **146 ms of avoided overhead per warm decision** in that test.
It does not multiply the engine's iterations per second by the same ratio.
Long searches benefit less proportionally.
[Raw measurements](benchmarks/2026-11-12-dispatch.csv) include both the isolation
test and a repeat after rebuilding the optimized native extension.

To repeat a fresh-versus-reused comparison with your installed engine:

```sh
python scripts/benchmark_dispatch.py
```

Four samples and their existing policy aggregation remain unchanged. The search
budget is per sample: four samples on two workers take approximately two waves
of the configured time, plus preparation and cleanup. Increasing parallelism
beyond available CPU cores can reduce throughput.

## Further work to measure

- Instruction generation and copying in the native engine still allocate
  substantially. Reusing buffers or sharing instruction prefixes needs separate
  correctness and performance work.
- Each turn starts fresh trees. Reusing a tree across turns would require
  matching the actual observed state and sampled hidden information.
- The native calls currently hold Python's GIL. Replacing the process pool with
  Python threads requires changing the bindings to release the GIL first.

No search depth, sample count, move pruning, evaluation weights, or Champions
mechanics were changed for these optimizations.
