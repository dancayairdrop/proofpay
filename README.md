# ProofPay — AI-adjudicated bounty escrow on GenLayer

ProofPay is a trustless bounty platform. A sponsor locks GEN in an **Intelligent
Contract** together with plain-English acceptance criteria. A hunter submits a
URL that proves the work is done (a merged GitHub PR, a live demo, a published
post…). Then **anyone** can trigger `resolve`, and the contract itself:

1. **fetches the submission page from the live web** — `gl.nondet.web.get(url)`
2. **asks an LLM whether the page satisfies the criteria** — `gl.nondet.exec_prompt(...)`
3. **reaches validator consensus on the decision** — `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`

If the network agrees the work is valid, the escrow is released to the hunter's
wallet automatically. **No human arbiter, no oracle, no off-chain server.**

> Why this needs GenLayer: reading arbitrary web pages and making a *subjective*
> "does this satisfy the criteria?" judgement is impossible on a deterministic
> chain — every node would compute a different answer and consensus would fail.
> GenLayer's Equivalence Principle is what makes an on-chain AI judge possible,
> and it is the core of ProofPay's entire workflow.

---

## What's in the box

```
proofpay/
├── contracts/
│   └── bounty_escrow.py          # The Intelligent Contract (the heart of the app)
├── tests/
│   ├── direct/                   # In-memory tests with mocked web + LLM (fast)
│   └── integration/              # End-to-end tests against a live network (gltest)
├── deploy/
│   └── deploy.mjs                # Deploy with GenLayerJS, writes address to app/.env
├── app/                          # Vite frontend that talks to the contract via GenLayerJS
│   ├── index.html
│   └── src/{main.js, genlayer.js, styles.css}
├── gltest.config.yaml            # Test/deploy network config
├── requirements.txt              # genlayer-test + genvm-linter
└── package.json                  # deploy script deps (genlayer-js)
```

## The contract API

| Method | Kind | What it does |
| --- | --- | --- |
| `create_bounty(title, criteria)` | `write.payable` | Lock the sent GEN as a bounty with acceptance criteria |
| `submit_deliverable(bounty_id, url)` | `write` | Attach a URL proving the work is complete |
| `resolve(bounty_id)` | `write` | **AI adjudication** → pays hunter if approved, else reopens |
| `cancel_bounty(bounty_id)` | `write` | Sponsor reclaims escrow while still `OPEN` |
| `get_bounties()` / `get_bounty(id)` / `get_bounty_count()` | `view` | Read state |

Lifecycle: `OPEN → SUBMITTED → (PAID | back to OPEN)`, or `OPEN → REFUNDED`.

## Quick start

### 0. Prerequisites
- Python ≥ 3.8, Node.js ≥ 18
- A GenLayer environment: the easiest is [GenLayer Studio](https://studio.genlayer.com)
  (zero-setup) or a local [GenLayer Studio](https://docs.genlayer.com/developers/intelligent-contracts/tooling-setup) on `http://localhost:4000/api`.

### 1. Lint + test the contract
```bash
pip install -r requirements.txt
genvm-lint check contracts/bounty_escrow.py
pytest tests/direct/ -v            # fast, no server, mocks the AI
gltest tests/integration/ -v -s    # end-to-end against a live network
```

### 2. Deploy
```bash
npm install
cp .env.example .env                # choose GENLAYER_NETWORK
npm run deploy                      # deploys and writes app/.env for you
```

### 3. Run the frontend
```bash
cd app
npm install
# app/.env already has VITE_CONTRACT_ADDRESS from the deploy step
npm run dev                         # open the printed localhost URL
```

Post a bounty, submit a proof URL, and click **Run AI adjudication** to watch the
contract fetch the page, judge it, and settle the escrow on-chain.

## How adjudication reaches consensus

`resolve` uses the **leader/validator** pattern. The leader fetches the page and
runs the LLM to produce `{approved, confidence, reason}`. Each validator
independently re-runs the same evaluation and votes to accept only if its
`approved` decision matches the leader's. Free-text `reason` wording is *not*
part of consensus (two LLMs never phrase things identically) — only the boolean
decision must agree. If validators disagree, the network rotates the leader and
retries; if it still can't agree, the transaction goes undetermined and state is
not modified.

## Notes & limits
- Native-token payouts to a wallet (EOA) are external messages that settle on
  finalization. In Studio, balances are simulated in a local DB.
- Rejected submissions leave the funds locked and reopen the bounty so a hunter
  can try again; sponsors can `cancel_bounty` only while `OPEN`.
- The LLM prompt is intentionally strict; tune `criteria` wording to your needs.

## Built with
GenVM (Python Intelligent Contracts) · GenLayerJS · Vite · genlayer-test.
