# The e2e tier replays recorded slots, not the live model

The tier-3 end-to-end test drives the **real** orchestrator (`run → tailor_one → chain
→ ship + log`) but swaps the one live model turn for a `ReplayLLM` that hands back a
fixture's recorded `resume.slots.json`. We chose this over calling the real Anthropic API
in the default suite so the e2e is deterministic, free, and runnable offline/in CI: the
only non-determinism in the whole flow is the model, and the model's deliverable is just
the slots, so freezing the slots freezes the run while leaving every line of production
assembly, compilation, fit-check, honesty-check, ship, and logging code on the real path.

## Considered options

- **Call the real model every run (rejected).** Truest simulation, but metered, slow,
  network-dependent, and flaky — a CI suite that costs money and breaks when the model
  reword drifts by a word is a suite people learn to ignore.
- **Mock the whole chain (rejected).** Fast, but then the e2e proves nothing the unit
  tiers don't; the bugs we care about (geometry wrap, honesty trace, ship/log wiring) live
  in exactly the code a chain-mock would skip.
- **Replay recorded slots through the real chain (chosen).** Keeps the entire
  deterministic core under test; the seam is a single, honest interface (`emit → EmitResult`)
  identical to the live session's, so the prompt/response logging path is exercised verbatim.

## Consequences

- The replayed slots are the ones that actually shipped, so their fit verdict is stable: a
  react turn can't improve them and the run ships them at the pass cap — which is precisely
  the real accept-after-cap behavior, so `WRAP`/`shippable` are exercised, not faked.
- The e2e cannot catch model-side regressions (a worse reword, a hallucinated number). That
  gap is covered deliberately by the one `@pytest.mark.live` smoke test — the real API, hand-run
  with a key, self-skipping otherwise — and by the dataset benchmark pairs, not by the suite.
