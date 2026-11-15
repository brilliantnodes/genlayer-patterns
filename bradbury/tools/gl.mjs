// Bradbury runner (genlayer-js). Usage:
//   node gl.mjs deploy <contract.py> '<json args>'
//   node gl.mjs write <address> <fn> '<json args>'
//   node gl.mjs read <address> <fn> '<json args>'
// Prints one JSON line. The key is read from a file and never printed.
import fs from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { TransactionStatus } from "genlayer-js/types";

const key = fs.readFileSync(process.env.BRADBURY_KEY_FILE, "utf8").trim();
const account = createAccount(key.startsWith("0x") ? key : "0x" + key);
const RPC = process.env.GL_RPC || "https://rpc-bradbury.genlayer.com";
const chain = { ...testnetBradbury, rpcUrls: { default: { http: [RPC] } } };
const client = createClient({ chain, account });
const [cmd, a1, a2, a3] = process.argv.slice(2);
const big = (_, v) => (typeof v === "bigint" ? v.toString() : v);
const out = (o) => console.log(JSON.stringify(o, big));

async function receipt(hash) {
  const r = await client.waitForTransactionReceipt({ hash, status: TransactionStatus.ACCEPTED, interval: 5000, retries: 240 });
  return r;
}
function brief(r) {
  const o = {};
  for (const k of ["statusName", "status_name", "status", "result", "resultName", "txExecutionResultName", "recipient", "to_address", "toAddress", "txId"]) if (r?.[k] !== undefined) o[k] = r[k];
  o.keys = Object.keys(r || {}).slice(0, 60);
  return o;
}
try {

  if (cmd === "deploy") {
    const code = fs.readFileSync(a1, "utf8");
    const t0 = Date.now();
    const est = await client.estimateTransactionFees();
    console.error("fee estimate (GEN):", Number(est.feeValue) / 1e18);
    const hash = await client.deployContract({ code, args: JSON.parse(a2 || "[]"), leaderOnly: false, fees: est });
    const r = await receipt(hash);
    out({ ok: true, hash, secs: Math.round((Date.now() - t0) / 1000), receipt: brief(r), raw: r });
  } else if (cmd === "write") {
    const t0 = Date.now();
    const est = await client.estimateTransactionFees();
    console.error("fee estimate (GEN):", Number(est.feeValue) / 1e18);
    const hash = await client.writeContract({ address: a1, functionName: a2, args: JSON.parse(a3 || "[]"), value: 0n, fees: est });
    const r = await receipt(hash);
    out({ ok: true, hash, secs: Math.round((Date.now() - t0) / 1000), receipt: brief(r), raw: r });
  } else if (cmd === "read") {
    out({ ok: true, result: await client.readContract({ address: a1, functionName: a2, args: JSON.parse(a3 || "[]") }) });
  } else if (cmd === "tx") {
    out({ ok: true, raw: await client.getTransaction({ hash: a1 }) });
  }
} catch (e) {
  out({ ok: false, error: String(e?.message || e).slice(0, 1500) });
  process.exit(1);
}
