/**
 * Deploy the ProofPay BountyEscrow contract with GenLayerJS.
 *
 *   node deploy/deploy.mjs
 *
 * Env vars (see .env.example):
 *   GENLAYER_NETWORK   localnet | studionet | testnetAsimov | testnetBradbury  (default: localnet)
 *   GENLAYER_ACCOUNT_PRIVATE_KEY   optional; a random funded account is used if unset (Studio only)
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createClient, createAccount } from "genlayer-js";
import * as chains from "genlayer-js/chains";
import { TransactionStatus } from "genlayer-js/types";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");

const networkName = process.env.GENLAYER_NETWORK || "localnet";
const chain = chains[networkName];
if (!chain) {
  throw new Error(`Unknown network "${networkName}". Use one of: ${Object.keys(chains).join(", ")}`);
}

const pk = process.env.GENLAYER_ACCOUNT_PRIVATE_KEY;
const account = pk ? createAccount(pk) : createAccount();

const client = createClient({ chain, account });

const code = readFileSync(join(root, "contracts", "bounty_escrow.py"), "utf8");

console.log(`Deploying BountyEscrow to ${networkName} as ${account.address} ...`);

const txHash = await client.deployContract({
  code,
  args: [], // __init__ takes no args
});

console.log(`Deploy tx: ${txHash}`);

const receipt = await client.waitForTransactionReceipt({
  hash: txHash,
  status: TransactionStatus.FINALIZED,
});

const contractAddress = receipt.data?.contract_address || receipt.contractAddress || receipt.contract_address;
console.log("Contract deployed at:", contractAddress);

// Persist the address so the frontend can pick it up.
const envPath = join(root, "app", ".env");
writeFileSync(
  envPath,
  `VITE_CONTRACT_ADDRESS=${contractAddress}\nVITE_GENLAYER_NETWORK=${networkName}\n`,
);
console.log(`Wrote ${envPath}`);
