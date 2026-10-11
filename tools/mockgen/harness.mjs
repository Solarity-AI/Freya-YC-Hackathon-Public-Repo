// Node harness for the bank mock engine (mock/src/engine.js): no wrangler, no network.
//
//   node tools/mockgen/harness.mjs run   < script.json        one batch of requests -> JSON results on stdout
//   node tools/mockgen/harness.mjs serve --dir mock --port 8787 [--kv|--memory]   local HTTP server (same routes as
//               the Worker). Default storage is an emulated Durable Object namespace (LEDGER_DO), like production.
//
// script.json: {"dir": "<mock dir with config.json, openapi.json, customers.json>"   (or "config"/"openapi"/"customers"
//               inline), "do": true|false (an emulated Durable Object namespace, LEDGER_DO; wins over KV),
//               "kv": true|false (a fake KV namespace), "kv_fail": false (every KV call throws),
//               "start_ms": 1760000000000, "steps": [{"method","path","body","headers"} | {"advance_s": 30}]}
// stdout:      [{"status": 200, "body": {...}|null}, ...]   (one entry per request step; advance steps give null)
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENGINE = path.resolve(HERE, "../../mock/src/engine.js");

function readJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")); }

function loadData(spec) {
  if (spec.dir) {
    return { config: readJson(path.join(spec.dir, "config.json")), openapi: readJson(path.join(spec.dir, "openapi.json")),
      customers: readJson(path.join(spec.dir, "customers.json")) };
  }
  return { config: spec.config || {}, openapi: spec.openapi || {}, customers: spec.customers || [] };
}

export function fakeKV({ fail = false } = {}) {
  const m = new Map();
  const boom = () => { throw new Error("KV unavailable (simulated)"); };
  return {
    _map: m,
    async get(k) { if (fail) boom(); return m.has(k) ? m.get(k) : null; },
    async put(k, v) { if (fail) boom(); m.set(k, String(v)); },
    async delete(k) { if (fail) boom(); m.delete(k); },
    async list({ prefix = "" } = {}) { if (fail) boom(); return { keys: [...m.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true }; },
  };
}

// Emulated Durable Object namespace: one storage Map per idFromName(name), surviving "reset_memory" (DO storage is
// durable); stub.fetch runs the engine with env.__store = that storage, exactly as the Ledger class in worker.js does.
export function fakeDO(mock, baseEnv) {
  const stores = new Map();
  const storageFor = (name) => {
    if (!stores.has(name)) {
      const m = new Map();
      stores.set(name, {
        _map: m,
        async get(k) { return m.has(k) ? m.get(k) : undefined; },
        async put(k, v) { m.set(k, v); },
        async delete(k) { return m.delete(k); },
        async deleteAll() { m.clear(); },
        async list({ prefix = "" } = {}) { return new Map([...m.entries()].filter(([k]) => k.startsWith(prefix)).sort()); },
      });
    }
    return stores.get(name);
  };
  return {
    _stores: stores,
    idFromName(name) { return { name: String(name), toString() { return "do:" + this.name; } }; },
    get(id) {
      return { fetch: (req) => mock.fetch(req, { ADMIN_TOKEN: baseEnv.ADMIN_TOKEN, __store: storageFor(id.name) }) };
    },
  };
}

async function run() {
  const spec = JSON.parse(fs.readFileSync(0, "utf8"));
  const { createMock, _resetMemory } = await import(ENGINE);
  _resetMemory();
  let t = Number(spec.start_ms || Date.parse("2026-10-14T11:00:00Z"));
  const mock = createMock({ ...loadData(spec), clock: () => t });
  const env = {};
  if (spec.kv || spec.kv_fail) env.LEDGER = fakeKV({ fail: !!spec.kv_fail });
  if (spec.admin_token) env.ADMIN_TOKEN = spec.admin_token;
  if (spec.do) env.LEDGER_DO = fakeDO(mock, env);
  const out = [];
  for (const step of spec.steps || []) {
    if (step.advance_s !== undefined) { t += Number(step.advance_s) * 1000; out.push(null); continue; }
    if (step.reset_memory) { _resetMemory(); out.push(null); continue; }   // a fresh isolate: only KV/DO survive
    const method = (step.method || "POST").toUpperCase();
    const init = { method, headers: { "content-type": "application/json", ...(step.headers || {}) } };
    if (step.raw !== undefined) init.body = step.raw;
    else if (step.body !== undefined && method !== "GET" && method !== "HEAD") init.body = JSON.stringify(step.body);
    const res = await mock.fetch(new Request("https://mock.test" + (step.path || "/"), init), env);
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    const entry = { status: res.status, body };
    if (step.want_headers) entry.headers = Object.fromEntries(res.headers.entries());
    out.push(entry);
  }
  process.stdout.write(JSON.stringify(out));
}

async function serve(argv) {
  const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
  const dir = path.resolve(arg("--dir", path.resolve(HERE, "../../mock")));
  const port = Number(arg("--port", "8787"));
  const { createMock } = await import(ENGINE);
  const mock = createMock(loadData({ dir }));
  const env = {};
  if (argv.includes("--kv")) env.LEDGER = fakeKV();
  else if (!argv.includes("--memory")) env.LEDGER_DO = fakeDO(mock, env);
  http.createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const init = { method: req.method, headers: req.headers };
    if (!["GET", "HEAD"].includes(req.method) && body.length) init.body = body;
    const r = await mock.fetch(new Request(`http://localhost:${port}${req.url}`, init), env);
    res.writeHead(r.status, Object.fromEntries(r.headers.entries()));
    res.end(Buffer.from(await r.arrayBuffer()));
  }).listen(port, () => process.stdout.write(`bank mock on http://localhost:${port} (data: ${dir}, storage: ${
    env.LEDGER_DO ? "durable_object (emulated)" : env.LEDGER ? "kv (fake)" : "memory"})\n`));
}

const mode = process.argv[2] || "run";
(mode === "serve" ? serve(process.argv.slice(3)) : run()).catch((e) => {
  process.stderr.write(String((e && e.stack) || e) + "\n");
  process.exit(1);
});
