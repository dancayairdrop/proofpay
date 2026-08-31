// Thin wrapper around GenLayerJS for the ProofPay frontend.
import { createClient, createAccount } from "genlayer-js";
import * as chains from "genlayer-js/chains";
import { TransactionStatus } from "genlayer-js/types";

const NETWORK = import.meta.env.VITE_GENLAYER_NETWORK || "localnet";
export const CONTRACT_ADDRESS = import.meta.env.VITE_CONTRACT_ADDRESS || "";

const chain = chains[NETWORK];
if (!chain) throw new Error(`Unknown GenLayer network: ${NETWORK}`);

// A burner account is fine for Studio / Localnet (fund it with the Studio
// faucet). For testnet, wire this to MetaMask via `provider: window.ethereum`.
const account = createAccount();

const client = createClient({ chain, account });

export const wallet = account.address;
export const networkName = NETWORK;

export async function getBounties() {
  if (!CONTRACT_ADDRESS) return [];
  const raw = await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_bounties",
    args: [],
  });
  return (raw || []).map(normalizeBounty);
}

export async function createBounty(title, criteria, rewardGen) {
  const value = BigInt(Math.round(Number(rewardGen) * 1e6)) * BigInt(10) ** BigInt(12); // GEN -> wei
  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName: "create_bounty",
    args: [title, criteria],
    value,
  });
  return waitFinal(hash);
}

export async function submitDeliverable(bountyId, url) {
  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName: "submit_deliverable",
    args: [BigInt(bountyId), url],
    value: BigInt(0),
  });
  return waitFinal(hash);
}

export async function resolveBounty(bountyId) {
  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName: "resolve",
    args: [BigInt(bountyId)],
    value: BigInt(0),
  });
  return waitFinal(hash);
}

export async function cancelBounty(bountyId) {
  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName: "cancel_bounty",
    args: [BigInt(bountyId)],
    value: BigInt(0),
  });
  return waitFinal(hash);
}

async function waitFinal(hash) {
  return client.waitForTransactionReceipt({
    hash,
    status: TransactionStatus.FINALIZED,
  });
}

function toNum(x) {
  try {
    return typeof x === "bigint" ? Number(x) : Number(x ?? 0);
  } catch {
    return 0;
  }
}

function normalizeBounty(b) {
  // GenLayerJS decodes the dataclass into a plain object; numbers arrive as bigint.
  return {
    id: toNum(b.id),
    sponsor: String(b.sponsor ?? ""),
    hunter: String(b.hunter ?? ""),
    title: b.title ?? "",
    criteria: b.criteria ?? "",
    submissionUrl: b.submission_url ?? "",
    reward: (toNum(b.reward) / 1e18).toFixed(4),
    status: b.status ?? "OPEN",
    verdict: b.verdict ?? "",
    confidence: toNum(b.confidence),
    attempts: toNum(b.attempts),
  };
}
