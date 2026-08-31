import {
  CONTRACT_ADDRESS,
  wallet,
  networkName,
  getBounties,
  createBounty,
  submitDeliverable,
  resolveBounty,
  cancelBounty,
} from "./genlayer.js";

const $ = (id) => document.getElementById(id);

function toast(msg, kind = "info") {
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  setTimeout(() => (t.className = "toast"), 4000);
}

function short(addr) {
  if (!addr || addr.length < 12) return addr || "—";
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

const STATUS_CLASS = {
  OPEN: "st-open",
  SUBMITTED: "st-submitted",
  PAID: "st-paid",
  REFUNDED: "st-refunded",
};

function renderWallet() {
  $("wallet").innerHTML = `
    <span class="net">${networkName}</span>
    <span class="addr" title="${wallet}">${short(wallet)}</span>`;
}

function bountyCard(b) {
  const isSponsor = b.sponsor.toLowerCase() === wallet.toLowerCase();
  const canCancel = isSponsor && b.status === "OPEN";
  const canSubmit = b.status === "OPEN" || b.status === "SUBMITTED";
  const canResolve = b.status === "SUBMITTED";

  return `
  <article class="card ${STATUS_CLASS[b.status] || ""}">
    <div class="card-top">
      <h3>#${b.id} · ${escapeHtml(b.title)}</h3>
      <span class="badge">${b.status}</span>
    </div>
    <p class="criteria">${escapeHtml(b.criteria)}</p>
    <dl class="meta">
      <div><dt>Reward</dt><dd>${b.reward} GEN</dd></div>
      <div><dt>Sponsor</dt><dd>${short(b.sponsor)}</dd></div>
      <div><dt>Hunter</dt><dd>${b.hunter && !/^0x0+$/.test(b.hunter) ? short(b.hunter) : "—"}</dd></div>
      <div><dt>Attempts</dt><dd>${b.attempts}</dd></div>
    </dl>
    ${b.submissionUrl ? `<p class="sub">Submission: <a href="${b.submissionUrl}" target="_blank" rel="noreferrer">${escapeHtml(b.submissionUrl)}</a></p>` : ""}
    ${b.verdict ? `<p class="verdict">🤖 AI verdict (${b.confidence}%): ${escapeHtml(b.verdict)}</p>` : ""}
    <div class="actions">
      ${canSubmit ? `<button data-act="submit" data-id="${b.id}">Submit proof</button>` : ""}
      ${canResolve ? `<button data-act="resolve" data-id="${b.id}" class="primary">Run AI adjudication</button>` : ""}
      ${canCancel ? `<button data-act="cancel" data-id="${b.id}" class="ghost">Cancel & refund</button>` : ""}
    </div>
  </article>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function refresh() {
  const box = $("bounties");
  if (!CONTRACT_ADDRESS) {
    box.innerHTML = `<div class="empty">No contract configured. Set <code>VITE_CONTRACT_ADDRESS</code> in <code>app/.env</code> (run <code>npm run deploy</code>).</div>`;
    return;
  }
  box.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    const list = await getBounties();
    box.innerHTML = list.length
      ? list.slice().reverse().map(bountyCard).join("")
      : `<div class="empty">No bounties yet. Post the first one →</div>`;
  } catch (e) {
    box.innerHTML = `<div class="empty error">Failed to load: ${escapeHtml(e.message)}</div>`;
  }
}

async function onAction(e) {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = Number(btn.dataset.id);
  const act = btn.dataset.act;
  btn.disabled = true;
  try {
    if (act === "submit") {
      const url = prompt("Paste the URL that proves the work is done (GitHub PR, demo, post…):");
      if (!url) return;
      toast("Submitting deliverable…");
      await submitDeliverable(id, url);
      toast("Submitted ✓", "ok");
    } else if (act === "resolve") {
      toast("Running on-chain AI adjudication… this reads the page + LLM + consensus.");
      await resolveBounty(id);
      toast("Adjudication finalized ✓", "ok");
    } else if (act === "cancel") {
      toast("Cancelling & refunding…");
      await cancelBounty(id);
      toast("Refunded ✓", "ok");
    }
    await refresh();
  } catch (err) {
    toast(err.message || "Transaction failed", "err");
  } finally {
    btn.disabled = false;
  }
}

$("create-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = $("f-title").value.trim();
  const criteria = $("f-criteria").value.trim();
  const reward = $("f-reward").value;
  if (!CONTRACT_ADDRESS) return toast("Set VITE_CONTRACT_ADDRESS first", "err");
  const submitBtn = e.target.querySelector("button");
  submitBtn.disabled = true;
  try {
    toast("Funding bounty on GenLayer…");
    await createBounty(title, criteria, reward);
    e.target.reset();
    $("f-reward").value = "1";
    toast("Bounty funded ✓", "ok");
    await refresh();
  } catch (err) {
    toast(err.message || "Failed to create bounty", "err");
  } finally {
    submitBtn.disabled = false;
  }
});

$("bounties").addEventListener("click", onAction);
$("refresh").addEventListener("click", refresh);

renderWallet();
refresh();
