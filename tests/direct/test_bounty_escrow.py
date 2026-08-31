"""Direct-mode tests for the ProofPay bounty escrow contract.

Direct mode runs the contract in-memory (no GenLayer node required) and lets us
mock the non-deterministic web + LLM calls, so the AI-adjudication logic is
tested deterministically.

Run:  pytest tests/direct/ -v
"""

import json

CONTRACT = "contracts/bounty_escrow.py"

ONE_GEN = 10**18


# ---------------------------------------------------------------------------
# Happy path: fund -> submit -> AI approves -> bounty is PAID
# ---------------------------------------------------------------------------
def test_create_submit_and_ai_approves(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)

    # Alice funds a bounty with 2 GEN
    direct_vm.sender = direct_alice
    direct_vm.value = 2 * ONE_GEN
    bounty_id = contract.create_bounty(
        "Fix the login bug",
        "A merged pull request that fixes the reported login crash.",
    )
    assert int(bounty_id) == 0

    direct_vm.value = 0

    # Bob submits a deliverable URL
    direct_vm.sender = direct_bob
    contract.submit_deliverable(bounty_id, "https://github.com/acme/app/pull/42")

    b = contract.get_bounty(bounty_id)
    assert b["status"] == "SUBMITTED"

    # Mock the web fetch of the PR page and the LLM verdict
    direct_vm.mock_web(
        r".*github\.com/acme/app/pull/42.*",
        {"status": 200, "body": "Merged pull request #42: fix login crash. Status: Merged."},
    )
    direct_vm.mock_llm(
        r".*impartial reviewer.*",
        json.dumps({"approved": True, "confidence": 92, "reason": "PR is merged and fixes the crash."}),
    )

    # Anyone can resolve; the AI decides
    contract.resolve(bounty_id)

    b = contract.get_bounty(bounty_id)
    assert b["status"] == "PAID"
    assert int(b["confidence"]) == 92
    assert int(b["attempts"]) == 1


# ---------------------------------------------------------------------------
# Rejection path: AI rejects -> bounty reopens, funds stay locked
# ---------------------------------------------------------------------------
def test_ai_rejects_reopens_bounty(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)

    direct_vm.sender = direct_alice
    direct_vm.value = ONE_GEN
    bounty_id = contract.create_bounty(
        "Write a benchmark blog post",
        "A published blog post with reproducible benchmark numbers.",
    )
    direct_vm.value = 0

    direct_vm.sender = direct_bob
    contract.submit_deliverable(bounty_id, "https://example.com/empty")

    direct_vm.mock_web(
        r".*example\.com/empty.*",
        {"status": 200, "body": "404 Not Found"},
    )
    direct_vm.mock_llm(
        r".*impartial reviewer.*",
        json.dumps({"approved": False, "confidence": 10, "reason": "Page is empty / not found."}),
    )

    contract.resolve(bounty_id)

    b = contract.get_bounty(bounty_id)
    assert b["status"] == "OPEN"          # reopened for another attempt
    assert int(b["attempts"]) == 1


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------
def test_zero_value_bounty_reverts(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    direct_vm.value = 0
    with direct_vm.expect_revert("funded with GEN"):
        contract.create_bounty("no money", "should fail")


def test_only_sponsor_can_cancel(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    direct_vm.value = ONE_GEN
    bounty_id = contract.create_bounty("Task", "Some criteria")
    direct_vm.value = 0

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only the sponsor can cancel"):
        contract.cancel_bounty(bounty_id)


def test_resolve_requires_submission(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    direct_vm.value = ONE_GEN
    bounty_id = contract.create_bounty("Task", "Some criteria")
    direct_vm.value = 0
    with direct_vm.expect_revert("nothing to resolve"):
        contract.resolve(bounty_id)
