# ProofPay architecture

```
        ┌─────────────┐  create_bounty(value=GEN)   ┌────────────────────────────┐
Sponsor │  Frontend   │ ──────────────────────────▶ │                            │
        │ (Vite +     │  cancel_bounty              │   BountyEscrow             │
        │  GenLayerJS)│ ◀────────── get_bounties ── │   Intelligent Contract     │
        └─────────────┘                             │   (contracts/              │
        ┌─────────────┐  submit_deliverable(url)    │    bounty_escrow.py)       │
Hunter  │  Frontend   │ ──────────────────────────▶ │                            │
        └─────────────┘                             │   state: DynArray[Bounty]  │
        ┌─────────────┐  resolve(id)  (permissionless)                          │
Anyone  │  Frontend   │ ──────────────────────────▶ │                            │
        └─────────────┘                             └──────────────┬─────────────┘
                                                                   │ resolve() runs a
                                                                   │ non-deterministic block
                                                                   ▼
                                        ┌──────────────────────────────────────────┐
                                        │  Equivalence Principle (consensus)         │
                                        │                                            │
                                        │  leader_fn():                              │
                                        │    page = gl.nondet.web.get(url)  ◀── live web
                                        │    v = gl.nondet.exec_prompt(...) ◀── LLM   │
                                        │    return {approved, confidence, reason}   │
                                        │                                            │
                                        │  validator_fn(leader):                     │
                                        │    re-run, agree only on `approved`        │
                                        └───────────────────┬────────────────────────┘
                                                            │ accepted decision
                                                            ▼
                                     approved → status=PAID, emit_transfer(reward→hunter)
                                     rejected → status=OPEN (funds stay locked, retry)
```

## Design decisions

**GenLayer is the workflow, not a feature.** The entire product exists because
an Intelligent Contract can read the open web and make a subjective judgement
under consensus. Remove GenLayer and there is no product — you'd need a trusted
oracle or human arbiter, which is exactly what ProofPay eliminates.

**Custom validator over `strict_eq`.** LLM output is non-deterministic, so we use
`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` and compare only the decision
field (`approved`). This is the recommended pattern for AI adjudication: tolerate
wording differences, agree on the outcome.

**Read web *inside* the nondet block.** Raw web bytes differ per node and are
expensive to store on-chain, so fetch → LLM-extract → return a small structured
decision, all within one non-deterministic function. Storage fields are copied
into locals before the block because storage isn't readable from inside it.

**Escrow safety.** Funds are only released on an `approved` consensus decision.
Rejections keep funds locked and reopen the bounty. Only the sponsor can cancel,
and only while `OPEN`. Payout uses an external message to the hunter's EOA, which
settles on finalization.

**State layout.** `DynArray[Bounty]` gives ordered, index-addressable bounties
(`bounty_id == index`). `Bounty` is an `@allow_storage @dataclass` with typed
fields (`u256` for GEN amounts, `Address` for parties, `str` for status/verdict).

## Files
- `contracts/bounty_escrow.py` — the Intelligent Contract.
- `app/src/genlayer.js` — GenLayerJS client + read/write helpers.
- `app/src/main.js` — UI state, rendering, and action handlers.
- `deploy/deploy.mjs` — deploy via `client.deployContract` and persist address.
- `tests/direct/` — in-memory tests mocking `mock_web` / `mock_llm`.
- `tests/integration/` — `gltest` end-to-end lifecycle test.
