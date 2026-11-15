import fs from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
const key = fs.readFileSync(process.env.BRADBURY_KEY_FILE, "utf8").trim();
const chain = { ...testnetBradbury, rpcUrls: { default: { http: ["https://rpc-bradbury.genlayer.com"] } } };
const client = createClient({ chain, account: createAccount(key.startsWith("0x") ? key : "0x" + key) });
const [addr, fn, args] = process.argv.slice(2);
try { const r = await client.simulateWriteContract({ address: addr, functionName: fn, args: JSON.parse(args) }); console.log("RETURNED", JSON.stringify(r, (_, v) => typeof v === "bigint" ? v.toString() : v).slice(0, 600)); }
catch (e) { const m = String(e?.message || e); const hex = m.match(/ReturnData:\[\]uint8\{([^}]*)\}/); if (hex) { const b = Buffer.from(hex[1].split(",").map(x => parseInt(x.trim(), 16))); console.log("ERRBYTES", b.toString("latin1").replace(/[^\x20-\x7e]+/g, " ").slice(0, 400)); } else console.log("ERR", m.slice(0, 600)); }
