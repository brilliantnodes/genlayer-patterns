// Free load check on Bradbury Phase 2: gen_call {type: "deploy"} runs the
// constructor on the network's GenVM. No transaction. Method from
// genlayer-foundation/uptime contracts/load-check.mjs.
import { readFileSync } from "node:fs";
import { abi } from "genlayer-js";
const RPC = "https://rpc-bradbury.genlayer.com";
const ZERO = "0x0000000000000000000000000000000000000001";
async function rpc(method, params) {
  const res = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) });
  const body = await res.json();
  if (body.error) throw new Error(body.error.message ?? JSON.stringify(body.error));
  return body.result;
}
for (const spec of process.argv.slice(2)) {
  const [file, argsJson] = spec.split("::");
  const args = JSON.parse(argsJson || "[]");
  const code = readFileSync(file, "utf8");
  try {
    const data = abi.transactions.serialize([code, abi.calldata.encode(abi.calldata.makeCalldataObject(undefined, args, undefined)), false]);
    const r = await rpc("gen_call", [{ type: "deploy", from: ZERO, data, transaction_hash_variant: "latest-nonfinal" }]);
    const ok = r?.status?.code === 0;
    console.log(`${ok ? "ok  " : "FAIL"} ${file.split("/").pop()}  ${ok ? "constructor ran" : JSON.stringify(r?.status ?? r).slice(0, 300)}`);
  } catch (e) { console.log(`FAIL ${file.split("/").pop()}  ${String(e.message).slice(0, 300)}`); }
}
