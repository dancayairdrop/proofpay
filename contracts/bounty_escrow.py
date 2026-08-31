# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#
# ProofPay - AI-adjudicated bounty escrow
# --------------------------------------------------------------------------
# A sponsor locks GEN in the contract together with human-readable acceptance
# criteria. A hunter submits a URL that proves the work is done (a merged
# GitHub PR, a live demo, a blog post, etc.). Anyone can then call `resolve`,
# which makes the Intelligent Contract:
#   1. fetch the submission page from the live web   (gl.nondet.web.get)
#   2. ask an LLM whether the page satisfies the criteria (gl.nondet.exec_prompt)
#   3. reach validator consensus on the *decision*   (gl.vm.run_nondet_unsafe)
# If the network agrees the work is valid, the escrow is released to the
# hunter automatically. No human arbiter is involved -- the AI judgement runs
# on-chain and is verified by validators. This is the part that is impossible
# on a normal (deterministic) blockchain and is the reason ProofPay is built
# on GenLayer.

from genlayer import *
from dataclasses import dataclass
import json
import typing


# ---------------------------------------------------------------------------
# External-message interface used to pay a plain wallet (EOA). Sending GEN to
# an address on the chain layer is an "external message" and, per the docs,
# must go through the EVM contract interface even though the target is an EOA.
# ---------------------------------------------------------------------------
@gl.evm.contract_interface
class _Payee:
    class View:
        pass

    class Write:
        pass


# Bounty lifecycle states
OPEN = "OPEN"            # funded, waiting for a submission
SUBMITTED = "SUBMITTED"  # a hunter submitted a deliverable URL
PAID = "PAID"            # AI approved -> escrow released to hunter
REFUNDED = "REFUNDED"    # sponsor cancelled -> escrow returned


@allow_storage
@dataclass
class Bounty:
    id: u256
    sponsor: Address          # who funded the bounty (for refunds / display)
    hunter: Address           # who submitted the current deliverable
    title: str
    criteria: str             # plain-English acceptance criteria the AI checks
    submission_url: str       # URL the AI fetches and evaluates
    reward: u256              # amount of GEN (wei) held in escrow
    status: str
    verdict: str              # the AI's written reasoning from the last resolve
    confidence: u256          # AI confidence 0-100 from the last resolve
    attempts: u256            # how many times resolve() has run on this bounty


class BountyEscrow(gl.Contract):
    owner: Address
    bounties: DynArray[Bounty]

    def __init__(self):
        self.owner = gl.message.sender_address

    # ------------------------------------------------------------------ writes

    @gl.public.write.payable
    def create_bounty(self, title: str, criteria: str) -> u256:
        """Create and fund a bounty. The GEN sent with the call is the reward."""
        reward = gl.message.value
        if reward == u256(0):
            raise gl.vm.UserError("A bounty must be funded with GEN (value > 0)")
        if len(title) == 0 or len(criteria) == 0:
            raise gl.vm.UserError("title and criteria are required")

        bounty_id = u256(len(self.bounties))
        zero = Address(bytes(20))
        self.bounties.append(
            Bounty(
                id=bounty_id,
                sponsor=gl.message.sender_address,
                hunter=zero,
                title=title,
                criteria=criteria,
                submission_url="",
                reward=reward,
                status=OPEN,
                verdict="",
                confidence=u256(0),
                attempts=u256(0),
            )
        )
        return bounty_id

    @gl.public.write
    def submit_deliverable(self, bounty_id: u256, submission_url: str) -> None:
        """A hunter attaches a URL that proves the bounty work is complete."""
        b = self.bounties[bounty_id]
        if b.status not in (OPEN, SUBMITTED):
            raise gl.vm.UserError("bounty is not accepting submissions")
        if not submission_url.startswith("http"):
            raise gl.vm.UserError("submission_url must be an http(s) URL")

        b.hunter = gl.message.sender_address
        b.submission_url = submission_url
        b.status = SUBMITTED

    @gl.public.write
    def resolve(self, bounty_id: u256) -> None:
        """Adjudicate a submission with the AI and release escrow if it passes.

        Permissionless: anyone may trigger resolution. The honesty of the
        outcome comes from validator consensus on the AI decision, not from
        trusting the caller.
        """
        b = self.bounties[bounty_id]
        if b.status != SUBMITTED:
            raise gl.vm.UserError("nothing to resolve for this bounty")

        # Copy storage values into locals BEFORE the non-deterministic block:
        # storage is not readable from inside a nondet function.
        criteria = b.criteria
        title = b.title
        url = b.submission_url

        def leader_fn():
            page = gl.nondet.web.get(url)
            body = page.body[:8000]
            prompt = f"""You are an impartial reviewer for a software/work bounty.

BOUNTY TITLE: {title}

ACCEPTANCE CRITERIA (all must be satisfied):
{criteria}

Below is the text content fetched from the submission URL the worker provided
as proof the work is done ({url}):
---
{body}
---

Decide whether this page is credible evidence that ALL acceptance criteria are
met. Be strict: if the page does not clearly demonstrate the criteria, reject.

Respond with ONLY a JSON object, no markdown, in exactly this shape:
{{"approved": <true|false>, "confidence": <integer 0-100>, "reason": "<one or two sentence justification>"}}"""
            raw = gl.nondet.exec_prompt(prompt)
            return _parse_verdict(raw)

        def validator_fn(leader_result) -> bool:
            # Reject anything that errored on the leader.
            if not isinstance(leader_result, gl.vm.Return):
                return False
            leader = leader_result.calldata
            mine = leader_fn()
            # Validators only need to agree on the DECISION (approve/reject).
            # The free-text reason will differ wording-to-wording and is not
            # part of consensus.
            return bool(leader.get("approved")) == bool(mine.get("approved"))

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        approved = bool(result.get("approved"))
        confidence = int(result.get("confidence", 0))
        if confidence < 0:
            confidence = 0
        if confidence > 100:
            confidence = 100

        b.attempts = u256(int(b.attempts) + 1)
        b.verdict = str(result.get("reason", ""))
        b.confidence = u256(confidence)

        if approved:
            b.status = PAID
            # Release the escrow to the hunter's wallet (external message).
            _Payee(b.hunter).emit_transfer(value=b.reward)
        else:
            # Rejected: leave funds locked and re-open for another attempt.
            b.status = OPEN

    @gl.public.write
    def cancel_bounty(self, bounty_id: u256) -> None:
        """Sponsor reclaims escrow while the bounty is still unclaimed/open."""
        b = self.bounties[bounty_id]
        if gl.message.sender_address != b.sponsor:
            raise gl.vm.UserError("only the sponsor can cancel")
        if b.status not in (OPEN,):
            raise gl.vm.UserError("only OPEN bounties can be cancelled")
        b.status = REFUNDED
        _Payee(b.sponsor).emit_transfer(value=b.reward)

    # ------------------------------------------------------------------- views

    @gl.public.view
    def get_bounties(self) -> typing.Any:
        return self.bounties

    @gl.public.view
    def get_bounty(self, bounty_id: u256) -> typing.Any:
        return self.bounties[bounty_id]

    @gl.public.view
    def get_bounty_count(self) -> u256:
        return u256(len(self.bounties))


# ---------------------------------------------------------------------------
# Helper: turn an LLM response (which may be wrapped in ``` fences or contain
# stray prose) into a clean decision dict. Kept module-level and pure so it can
# be called from inside the non-deterministic block.
# ---------------------------------------------------------------------------
def _parse_verdict(raw: str) -> dict:
    text = raw.strip()
    if "```" in text:
        # strip the first fenced block
        parts = text.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)
    return {
        "approved": bool(data.get("approved", False)),
        "confidence": int(data.get("confidence", 0)),
        "reason": str(data.get("reason", "")),
    }
