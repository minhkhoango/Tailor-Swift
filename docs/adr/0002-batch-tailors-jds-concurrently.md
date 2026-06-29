# The batch tailors JDs concurrently, capped at 15

`run()` (and `why()`) fan their work-list across a `ThreadPoolExecutor` capped at
`MAX_WORKERS = 15`, instead of looping one JD at a time. Each JD is an independent,
**I/O-bound** chain — one or two Anthropic HTTP turns plus a `pdflatex` subprocess, both of
which release the GIL — so N JDs that took N × (network + compile) serially now finish in
roughly the time of the slowest single JD, up to 15 wide. The work-list is decided serially
first (the skip-already-done scan is a cheap stat, no API), so only JDs that need work are
fanned out; reports are reassembled in input order regardless of finish order.

## Why this is safe to parallelize

Nothing mutable is shared between JDs. Each JD gets its **own** `SlotSession` (fresh per
`session()` call), its **own** scratch dir `.tailor_cache/<stem>/` (pdflatex runs with that
dir as both cwd and `-output-directory`, with a per-stem jobname, so no aux-file or temp
collision), and writes only to its **own** `output/<stem>/` and `dataset/<stem>/`. The
Anthropic SDK client is itself thread-safe and is shared read-only. The one genuinely shared
resource is the run logger: it now holds a `threading.Lock` so each event's JSONL line and
its console echo emit as one unit and never interleave.

## Considered options

- **Keep it serial (rejected).** Simplest, but a 15-JD scrape run waits on 15 sequential
  network-plus-compile chains end to end — the dominant cost is wall-clock latency the user
  watches, and every JD is embarrassingly parallel.
- **`asyncio` (rejected).** The Anthropic call and `pdflatex` are sync; going async would
  mean an async SDK path and threading the subprocess through an executor anyway, for no gain
  over a thread pool on this I/O-bound, GIL-releasing workload.
- **`multiprocessing` (rejected).** Real parallelism, but the work already releases the GIL,
  so processes only add pickling, a separate SDK client per worker (cold prompt cache), and
  harder log multiplexing — cost with no upside here.
- **Thread pool, cap 15 (chosen).** Matches the workload (I/O-bound), keeps one warm
  prompt-cached client, and the only shared state needs just one lock.

## Consequences

- **Cap is a hard 15, no knob.** Bounds concurrent load on the Anthropic account (15 in-flight
  requests) and the machine (15 pdflatex processes). The pool also shrinks to `len(work-list)`,
  so a 3-JD batch spawns 3 threads. If rate limits bite, the SDK's own retry/backoff absorbs
  the 429s; the cap, not a config flag, is the throttle.
- **Failure is isolated, not fatal.** A blow-up in one JD (network drop, model error, an escaped
  compile failure) is caught per-worker, logged as a loud `error` event, and returned as a
  non-shippable `ERROR` report. The batch exit code is still non-zero, but the other 14 JDs in
  flight finish — one bad JD never cancels good work.
- **Console output interleaves at the JD granularity.** Lines stay whole (the logger lock), but
  two JDs' passes appear intermixed live. The JSONL stream is the ordered record of truth; the
  console echo is a progress glance, and `stem=` on every line keeps it readable.
- The honesty gate, pass cap, ship/abort rules, and skip-existing semantics are all unchanged —
  this ADR is purely about *how many JDs run at once*, not *what tailoring one JD does*.
