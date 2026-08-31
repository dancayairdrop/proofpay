"""End-to-end integration tests against a live GenLayer environment.

These deploy the real contract and drive it through JSON-RPC, so the LLM +
web calls execute for real and validators reach actual consensus.

Prerequisite: a running environment (GenLayer Studio / Localnet) configured in
gltest.config.yaml.

Run:  gltest tests/integration/ -v -s
"""

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

ONE_GEN = 10**18


def test_full_bounty_lifecycle():
    factory = get_contract_factory("BountyEscrow")
    contract = factory.deploy(args=[])

    # Fund a bounty (payable) with 1 GEN
    receipt = contract.create_bounty(
        args=["GenLayer docs star", "The linked GitHub repo has more than 1 star."],
        value=ONE_GEN,
    ).transact()
    assert tx_execution_succeeded(receipt)

    count = contract.get_bounty_count(args=[]).call()
    assert int(count) == 1

    # Submit a deliverable that clearly satisfies the criteria
    receipt = contract.submit_deliverable(
        args=[0, "https://github.com/genlayerlabs/genlayer-js"],
    ).transact()
    assert tx_execution_succeeded(receipt)

    # Resolve -> the network fetches the page, runs the LLM, and reaches
    # consensus on the decision. We assert the tx executed; the resulting
    # status depends on the live page + model judgement.
    receipt = contract.resolve(args=[0]).transact()
    assert tx_execution_succeeded(receipt)

    bounty = contract.get_bounty(args=[0]).call()
    assert bounty["status"] in ("PAID", "OPEN")
    assert int(bounty["attempts"]) == 1
