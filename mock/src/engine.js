// Generic bank-services mock engine (Cloudflare Worker, ES module). Owner: mock workstream (tools/mockgen).
//
// Everything case-specific lives in three data files written by tools/mockgen/make_config.py:
//   config.json    operations (method + path -> role), field roles, request leaf rules, response leaf names, statuses
//   customers.json [{customer_id, identity:{key: answer}, products:[...], account:{...}, variables:{...}, faults:[...]}]
//   openapi.json   served verbatim at /openapi.json (servers[0].url rewritten to this mock's origin)
// Roles: verify | account | promise | note | callback | transfer | close (same semantics as harness/mockbank.py).
// The ledger is per customer (plus an optional call key), one "session" per phone call. Storage, best first:
//   Durable Object (binding LEDGER_DO, class Ledger in worker.js): the Worker forwards every request that touches a
//     customer's ledger to the DO named after that customer id (idFromName), which runs this same engine with
//     env.__store = ctx.storage. One single-threaded writer per customer, transactional storage: strongly consistent.
//   Workers KV (binding LEDGER) with an in-isolate write-through copy: eventually consistent (legacy fallback).
//   isolate memory only (no binding): fine for a local smoke test.
// Never throws to the platform: an unexpected error answers 500 {ok:false, error:"service failed: ..."}.

export const ENGINE_VERSION = "1.0.0";

export const MESSAGES = {
  en: {
    not_verified: "identity not verified",
    closed: "the call is already closed",
    unknown_customer: "unknown customer_id",
    unknown_operation: "unknown operation",
    unknown_product: "unknown product_id",
    duplicate_promise: "this product already has a promise",
    duplicate_call_promise: "a promise is already recorded on this call",
    missing: "missing {field}",
    unknown_value: "unknown {field}",
    bad_type: "{field} must be a {type}",
    bad_pattern: "{field} has the wrong format",
    bad_length: "{field} has the wrong length",
    bad_range: "{field} is out of range",
    bad_date: "{field} must be {format}",
    bad_callback: "date must be YYYY-MM-DD and time HH:MM",
    amount_positive: "{field} must be more than zero",
    past_date: "{field} is in the past",
    amount_integer: "{field} must be an integer",
    unknown_field: "unknown field",
    no_answer: "no identity answer given",
    unreadable_date: "answer must be a date as YYYY-MM-DD",
    unreadable: "unreadable answer",
    too_many_wrong: "too many wrong answers",
    locked: "identity check is over: too many wrong answers",
    reason_required: "a reason is required for outcome {outcome}",
    reason_not_allowed: "reason for outcome {outcome} must be one of: {allowed}",
    service_failed: "the service failed",
    body_json: "body must be JSON",
    method: "method not allowed",
  },
  tr: {
    not_verified: "kimlik doğrulanmadı",
    closed: "görüşme zaten kapatıldı",
    unknown_customer: "bilinmeyen müşteri",
    unknown_operation: "bilinmeyen işlem",
    unknown_product: "bilinmeyen ürün",
    duplicate_promise: "bu ürün için zaten bir ödeme sözü var",
    duplicate_call_promise: "bu görüşmede zaten bir ödeme sözü kaydedildi",
    missing: "{field} eksik",
    unknown_value: "geçersiz {field}",
    bad_type: "{field} {type} olmalı",
    bad_pattern: "{field} biçimi hatalı",
    bad_length: "{field} uzunluğu hatalı",
    bad_range: "{field} izin verilen aralıkta değil",
    bad_date: "{field} {format} biçiminde olmalı",
    bad_callback: "tarih YYYY-AA-GG ve saat SS:DD biçiminde olmalı",
    amount_positive: "{field} sıfırdan büyük olmalı",
    past_date: "{field} geçmiş bir tarih",
    amount_integer: "{field} tam sayı olmalı",
    unknown_field: "bilinmeyen alan",
    no_answer: "kimlik cevabı yok",
    unreadable_date: "cevap YYYY-AA-GG biçiminde bir tarih olmalı",
    unreadable: "cevap okunamadı",
    too_many_wrong: "çok fazla yanlış cevap",
    locked: "kimlik doğrulama sona erdi: çok fazla yanlış cevap",
    reason_required: "{outcome} sonucu için bir neden gerekli",
    reason_not_allowed: "{outcome} sonucu için neden şunlardan biri olmalı: {allowed}",
    service_failed: "servis hatası",
    body_json: "gövde JSON olmalı",
    method: "yöntem desteklenmiyor",
  },
};

const DEFAULT_STATUSES = {
  ok: 200, invalid: 200, refused: 200, not_verified: 200, conflict: 200, locked: 200, closed: 200,
  unknown_product: 200, unknown_customer: 404, unknown_operation: 404, fault: 500,
};
const DEFAULT_SESSION = { idle_reset_s: 240, closed_grace_s: 15, new_call_on_verify_after_close: true,
  key_fields: [], key_headers: [], history: 20 };
// message key -> error kind (config.error_codes maps a kind to the code the contract documents for it)
export const ERR_KIND = {
  not_verified: "not_verified", closed: "closed", unknown_customer: "unknown_customer",
  unknown_product: "unknown_product", duplicate_promise: "duplicate", duplicate_call_promise: "duplicate",
  missing: "invalid_value", unknown_value: "invalid_value", bad_type: "invalid_value", bad_pattern: "format",
  bad_length: "format", bad_range: "invalid_value", bad_date: "format", bad_callback: "format",
  amount_positive: "invalid_value", amount_integer: "invalid_value", unknown_field: "invalid_value",
  no_answer: "format", unreadable_date: "format", unreadable: "format", too_many_wrong: "locked", locked: "locked",
  reason_required: "invalid_value", reason_not_allowed: "invalid_value", past_date: "invalid_value",
  service_failed: "fault",
};
const ROLES = ["verify", "account", "promise", "note", "callback", "transfer", "close", "stub"];

// ------------------------------------------------------------------------------------------------ small helpers

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const clone = (x) => (x === undefined ? undefined : JSON.parse(JSON.stringify(x)));
const empty = (v) => v === undefined || v === null || (typeof v === "string" && v.trim() === "");

export function fmt(template, vars) {
  return String(template).replace(/\{(\w+)\}/g, (_, k) => (vars && vars[k] !== undefined ? String(vars[k]) : ""));
}

const TR_FOLD = { "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I", "ö": "o", "Ö": "O", "ş": "s",
  "Ş": "S", "ü": "u", "Ü": "U", "â": "a", "Â": "A", "î": "i", "Î": "I", "û": "u", "Û": "U" };
export function fold(s) {
  return String(s ?? "").replace(/[çÇğĞıİöÖşŞüÜâÂîÎûÛ]/g, (c) => TR_FOLD[c]).normalize("NFKD")
    .replace(/[̀-ͯ]/g, "");
}

export function normAnswer(s, keepSpace) {
  const t = fold(s).trim().toUpperCase();
  return keepSpace ? t.replace(/\s+/g, " ") : t.replace(/\s+/g, "");
}

const pad = (n, w = 2) => String(n).padStart(w, "0");

export function validDate(y, m, d) {
  if (!(y >= 1000 && y <= 9999 && m >= 1 && m <= 12 && d >= 1 && d <= 31)) return false;
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

export function isIsoDate(s) {
  if (typeof s !== "string") return false;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return !!m && validDate(+m[1], +m[2], +m[3]);
}

// month names (language, not case content): English and Turkish, full and 3-letter forms
const MONTHS = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10,
  november: 11, december: 12, jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10,
  nov: 11, dec: 12,
  ocak: 1, subat: 2, mart: 3, nisan: 4, mayis: 5, haziran: 6, temmuz: 7, agustos: 8, eylul: 9, ekim: 10,
  kasim: 11, aralik: 12, oca: 1, sub: 2, nis: 4, haz: 6, tem: 7, agu: 8, eyl: 9, eki: 10, kas: 11, ara: 12,
};

// A spoken or written date -> "YYYY-MM-DD" or null. Numbers only are read day, month, year (unless the year is first).
export function parseLooseDate(s) {
  if (typeof s !== "string") s = s === undefined || s === null ? "" : String(s);
  const t = fold(s).trim().toLowerCase().replace(/(\d)(st|nd|rd|th)\b/g, "$1");
  let m = /^(\d{4})[-./ ](\d{1,2})[-./ ](\d{1,2})$/.exec(t);
  if (m) return validDate(+m[1], +m[2], +m[3]) ? `${m[1]}-${pad(m[2])}-${pad(m[3])}` : null;
  m = /^(\d{1,2})[-./ ](\d{1,2})[-./ ](\d{4})$/.exec(t);
  if (m) return validDate(+m[3], +m[2], +m[1]) ? `${m[3]}-${pad(m[2])}-${pad(m[1])}` : null;
  m = /^(\d{4})(\d{2})(\d{2})$/.exec(t);
  if (m) return validDate(+m[1], +m[2], +m[3]) ? `${m[1]}-${m[2]}-${m[3]}` : null;
  const words = t.replace(/[,.]/g, " ").split(/\s+/).filter(Boolean);
  if (words.length === 3) {
    let d, mo, y;
    if (/^\d{1,2}$/.test(words[0]) && MONTHS[words[1]] && /^\d{4}$/.test(words[2])) {
      d = +words[0]; mo = MONTHS[words[1]]; y = +words[2];
    } else if (MONTHS[words[0]] && /^\d{1,2}$/.test(words[1]) && /^\d{4}$/.test(words[2])) {
      mo = MONTHS[words[0]]; d = +words[1]; y = +words[2];
    } else if (/^\d{4}$/.test(words[0]) && MONTHS[words[1]] && /^\d{1,2}$/.test(words[2])) {
      y = +words[0]; mo = MONTHS[words[1]]; d = +words[2];
    }
    if (y && validDate(y, mo, d)) return `${y}-${pad(mo)}-${pad(d)}`;
  }
  return null;
}

// the same date read with day and month swapped ("02.14.1986" -> 1986-02-14, "1986-14-02" -> 1986-02-14) or null
export function swapDayMonth(s) {
  const t = String(s ?? "").trim();
  let m = /^(\d{4})([-./ ])(\d{1,2})\2(\d{1,2})$/.exec(t);
  if (m) return validDate(+m[1], +m[4], +m[3]) ? `${m[1]}-${pad(m[4])}-${pad(m[3])}` : null;
  m = /^(\d{1,2})([-./ ])(\d{1,2})\2(\d{4})$/.exec(t);
  if (m) return validDate(+m[4], +m[1], +m[3]) ? `${m[4]}-${pad(m[1])}-${pad(m[3])}` : null;
  return null;
}

// strict wire format check: "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d", "%H:%M", "%H:%M:%S",
// "%Y-%m-%dT%H:%M:%S" -> {date:"YYYY-MM-DD"|null, time:"HH:MM"|null} or null when the value does not fit
export function parseWire(value, wire) {
  if (typeof value !== "string") return null;
  const tokens = { "%Y": "(\\d{4})", "%m": "(\\d{2})", "%d": "(\\d{2})", "%H": "(\\d{2})", "%M": "(\\d{2})",
    "%S": "(\\d{2})" };
  const order = [];
  let rx = "";
  for (let i = 0; i < wire.length; i++) {
    const tk = wire.slice(i, i + 2);
    if (tokens[tk]) { rx += tokens[tk]; order.push(tk); i++; } else rx += wire[i].replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  }
  let m = new RegExp("^" + rx + "$").exec(value);
  if (!m && wire === "%Y-%m-%dT%H:%M:%S") m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})()(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/.exec(value);
  if (!m) return null;
  const v = {};
  order.forEach((tk, i) => { v[tk] = m[i + 1]; });
  if (wire === "%Y-%m-%dT%H:%M:%S" && order.length === 6 && m.length === 7 && m[6] === "") v["%S"] = "00";
  let date = null, time = null;
  if (v["%Y"] !== undefined) {
    if (!validDate(+v["%Y"], +v["%m"], +v["%d"])) return null;
    date = `${v["%Y"]}-${v["%m"]}-${v["%d"]}`;
  }
  if (v["%H"] !== undefined) {
    if (+v["%H"] > 23 || +v["%M"] > 59 || (v["%S"] !== undefined && +v["%S"] > 59)) return null;
    time = `${v["%H"]}:${v["%M"]}`;
  }
  return { date, time };
}

export function toNumber(v) {
  if (typeof v === "boolean" || v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && /^\s*-?\d+(\.\d+)?\s*$/.test(v)) return parseFloat(v);
  return null;
}

function safeDecode(s) {
  try { return decodeURIComponent(s); } catch { return s; }
}

function getPath(obj, path) {
  if (!path) return undefined;
  let cur = obj;
  for (const p of String(path).split(".")) {
    if (!isObj(cur)) return undefined;
    cur = cur[p];
  }
  return cur;
}

function setPath(obj, path, value) {
  const parts = String(path).split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!isObj(cur[parts[i]])) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}

// ------------------------------------------------------------------------------------------------ storage

const MEM = new Map();          // key -> {rev, raw}   (per isolate; survives between requests in one isolate)
const LOCKS = new Map();        // key -> promise chain (serialises read-modify-write inside one isolate)
const STATS = { kv_errors: 0, kv_last_error: null };

export function _resetMemory() { MEM.clear(); LOCKS.clear(); STATS.kv_errors = 0; STATS.kv_last_error = null; }

async function withLock(key, fn) {
  const prev = LOCKS.get(key) || Promise.resolve();
  let release;
  const next = new Promise((r) => { release = r; });
  const chain = prev.then(() => next);
  LOCKS.set(key, chain);
  await prev;
  try { return await fn(); } finally {
    release();
    if (LOCKS.get(key) === chain) LOCKS.delete(key);
  }
}

function kvError(e) { STATS.kv_errors += 1; STATS.kv_last_error = String((e && e.message) || e).slice(0, 200); }

// env.__store is a Durable Object's ctx.storage (set by the Ledger class): authoritative, no isolate copy needed.
async function storeGet(env, key) {
  if (env && env.__store) {
    const raw = await env.__store.get(key);
    return raw ? JSON.parse(raw) : null;
  }
  const mem = MEM.get(key);
  let best = mem ? JSON.parse(mem.raw) : null;
  if (env && env.LEDGER) {
    try {
      const raw = await env.LEDGER.get(key);
      if (raw) {
        const kv = JSON.parse(raw);
        if (!best || (kv.rev || 0) > (best.rev || 0)) best = kv;
      }
    } catch (e) { kvError(e); }
  }
  return best;
}

async function storePut(env, key, rec) {
  rec.rev = (rec.rev || 0) + 1;
  const raw = JSON.stringify(rec);
  if (env && env.__store) { await env.__store.put(key, raw); return; }
  MEM.set(key, { rev: rec.rev, raw });
  if (env && env.LEDGER) {
    try { await env.LEDGER.put(key, raw); } catch (e) { kvError(e); }
  }
}

async function storeDel(env, key) {
  if (env && env.__store) { await env.__store.delete(key); return; }
  MEM.delete(key);
  if (env && env.LEDGER) {
    try { await env.LEDGER.delete(key); } catch (e) { kvError(e); }
  }
}

async function storeKeys(env, prefix) {
  if (env && env.__store) return [...(await env.__store.list({ prefix })).keys()];
  const keys = new Set([...MEM.keys()].filter((k) => k.startsWith(prefix)));
  if (env && env.LEDGER && env.LEDGER.list) {
    try {
      let cursor;
      for (let i = 0; i < 20; i++) {
        const page = await env.LEDGER.list({ prefix, cursor });
        for (const k of page.keys || []) keys.add(k.name);
        if (page.list_complete || !page.cursor) break;
        cursor = page.cursor;
      }
    } catch (e) { kvError(e); }
  }
  return [...keys];
}

// ------------------------------------------------------------------------------------------------ the mock

export function createMock({ config, openapi, customers, clock } = {}) {
  const cfg = config || {};
  const lang = MESSAGES[cfg.lang] ? cfg.lang : "en";
  const MSG = { ...MESSAGES.en, ...MESSAGES[lang], ...(cfg.messages || {}) };
  const ST = { ...DEFAULT_STATUSES, ...(cfg.statuses || {}) };
  const CODES = isObj(cfg.error_codes) ? cfg.error_codes : {};
  const SESSION = { ...DEFAULT_SESSION, ...(cfg.session || {}) };
  const PRODUCTS = { list: "products", id: "product_id", type: "type", ...(cfg.products || {}) };
  const OPS = (cfg.ops || []).filter((o) => isObj(o) && ROLES.includes(o.role));
  const BASES = (cfg.base_paths || []).map((b) => String(b).replace(/\/+$/, "")).filter(Boolean)
    .sort((a, b) => b.length - a.length);
  const now = typeof clock === "function" ? clock : () => Date.now();
  const CUST = new Map();
  for (const c of customers || []) {
    if (!isObj(c)) continue;
    const id = c.customer_id ?? c.id;
    if (id !== undefined && id !== null && String(id) !== "") CUST.set(String(id), c);
  }
  const maxWrongFor = (cust) => Number(cust.max_wrong || cfg.max_wrong || 3);

  const headers = (extra) => ({
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "access-control-allow-headers": "*",
    "access-control-max-age": "86400",
    "cache-control": "no-store",
    ...(extra || {}),
  });
  const json = (obj, status = 200) => new Response(obj === null ? "" : JSON.stringify(obj), { status, headers: headers() });

  // ---- routing
  function compile(path) {
    const names = [];
    const rx = String(path).replace(/\/+$/, "").replace(/[.*+?^$()|[\]\\]/g, "\\$&")
      .replace(/\\?\{([^}/]+)\\?\}|\{([^}/]+)\}/g, (_, a, b) => { names.push(a || b); return "([^/]+)"; });
    return { rx: new RegExp("^" + (rx || "") + "$"), names };
  }
  // an operation with {param} segments is also reachable at the literal path without them (builder.contract sends
  // every call as POST + JSON body to that literal path), the parameters then coming from the body
  const ROUTES = [];
  for (const op of OPS) {
    const method = String(op.method || "POST").toUpperCase();
    ROUTES.push({ op, method, ...compile(op.path || "/") });
    const literal = String(op.path || "/").replace(/\/\{[^}/]*\}/g, "") || "/";
    if (literal !== op.path) ROUTES.push({ op, method: "POST", ...compile(literal) });
  }

  function route(method, path) {
    const tries = [path];
    for (const b of BASES) if (path.startsWith(b + "/")) tries.push(path.slice(b.length));
    // exact method first, then any method on the same path (a client may POST to a PUT/PATCH/GET operation)
    for (const exact of [true, false]) {
      for (const p of tries) {
        for (const r of ROUTES) {
          if (exact && r.method !== method) continue;
          const m = r.rx.exec(p);
          if (!m) continue;
          const params = {};
          r.names.forEach((n, i) => { try { params[n] = decodeURIComponent(m[i + 1]); } catch { params[n] = m[i + 1]; } });
          return { op: r.op, params };
        }
      }
    }
    // last resort: the request path ends with an operation path (an unexpected prefix in front of it)
    for (const r of ROUTES) {
      if (r.names.length) continue;
      const p = String(r.op.path).replace(/\/+$/, "");
      if (p && p !== "/" && path.endsWith(p)) return { op: r.op, params: {} };
    }
    return null;
  }

  // ---- ledger
  const freshSession = (n, t) => ({
    session: n, started_at: new Date(t).toISOString(), last_at_ms: t, verified: {}, wrong: 0, hinted: 0,
    promises: [], notes: [], callbacks: [], transfers: [], outcome: null, reason: null, closed: false,
    closed_at_ms: null, failures: {}, op_counts: {}, calls: [],
  });

  function sessionKey(op, args, request) {
    for (const f of SESSION.key_fields || []) if (!empty(args[f])) return String(args[f]);
    for (const h of SESSION.key_headers || []) {
      const v = request && request.headers && request.headers.get(h);
      if (v) return String(v);
    }
    return "";
  }
  const ledgerKey = (cid, skey) => "L:" + cid + (skey ? "::" + skey : "");

  function rollover(rec, role, t) {
    const cur = rec.current;
    if (!cur || !cur.calls.length) return;
    const idle = (t - (cur.last_at_ms || 0)) / 1000;
    let roll = idle > SESSION.idle_reset_s;
    if (!roll && cur.closed) {
      const since = (t - (cur.closed_at_ms || 0)) / 1000;
      roll = since > SESSION.closed_grace_s || (SESSION.new_call_on_verify_after_close && role === "verify");
    }
    if (roll) {
      rec.history = [...(rec.history || []), cur].slice(-Math.max(0, SESSION.history | 0));
      rec.current = freshSession((cur.session || 1) + 1, t);
    }
  }

  // ---- response building (leaf names from the contract; nested envelopes via dotted paths)
  // an error is {key, text}: the contract's error code for its kind when config.error_codes has one, else the text
  function msg(key, vars) { return { key, text: fmt(MSG[key] ?? key, vars) }; }
  function errValue(err) {
    if (err === undefined || err === null) return err;
    if (typeof err !== "object") return err;
    const kind = ERR_KIND[err.key] || err.key;
    if (CODES[kind] !== undefined) return CODES[kind];
    const sibling = { invalid_value: "format", format: "invalid_value" }[kind];
    if (sibling && CODES[sibling] !== undefined) return CODES[sibling];
    return err.text;
  }
  function respond(op, ok, err, roles) {
    const R = op.response || {};
    const out = {};
    // the success leaf is a boolean, or a status enum (s_values {ok, fail}) when the contract says so
    if (R.s) setPath(out, R.s, op.s_values ? (ok ? op.s_values.ok : op.s_values.fail) : !!ok);
    if (err !== undefined && err !== null) {
      setPath(out, R.err || "error", errValue(err));
      if (R.msg && typeof err === "object") setPath(out, R.msg, err.text);
    }
    for (const [role, val] of Object.entries(roles || {})) {
      if (R[role] && val !== undefined) setPath(out, R[role], val);
    }
    if (isObj(op.extra_ok) && ok) for (const [k, v] of Object.entries(op.extra_ok)) if (getPath(out, k) === undefined) setPath(out, k, v);
    return out;
  }
  const refuse = (op, kind, err, roles) => ({ status: ST[kind] ?? 200, body: respond(op, false, err, roles) });
  const okRes = (op, roles) => ({ status: ST.ok, body: respond(op, true, undefined, roles) });

  // ---- generic request validation from the contract's leaves
  function validate(op, args) {
    const req = op.request || {};
    for (const [f, leaf] of Object.entries(req)) {
      if (leaf.required && empty(args[f])) return msg("missing", { field: f });
    }
    for (const [f, leaf] of Object.entries(req)) {
      const v = args[f];
      if (empty(v)) continue;
      if (Array.isArray(leaf.enum) && leaf.enum.length && !leaf.enum.map(String).includes(String(v))) {
        return msg("unknown_value", { field: f });
      }
      const t = leaf.type;
      if ((t === "number" || t === "integer") && toNumber(v) === null) return msg("bad_type", { field: f, type: t === "integer" ? "integer" : "number" });
      if (t === "integer" && !Number.isInteger(toNumber(v))) return msg("amount_integer", { field: f });
      if (t === "boolean" && !(typeof v === "boolean" || v === "true" || v === "false")) return msg("bad_type", { field: f, type: "boolean" });
      const n = toNumber(v);
      if (n !== null && (t === "number" || t === "integer")) {
        if (leaf.minimum !== undefined && leaf.minimum !== null && n < leaf.minimum) return msg("bad_range", { field: f });
        if (leaf.maximum !== undefined && leaf.maximum !== null && n > leaf.maximum) return msg("bad_range", { field: f });
        if (leaf.exclusive_minimum !== undefined && leaf.exclusive_minimum !== null && n <= leaf.exclusive_minimum) return msg("bad_range", { field: f });
      }
      if (typeof v === "string") {
        if (leaf.min_length && v.length < leaf.min_length) return msg("bad_length", { field: f });
        if (leaf.max_length && v.length > leaf.max_length) return msg("bad_length", { field: f });
        if (leaf.pattern) {
          let rx = null;
          try { rx = new RegExp(leaf.pattern); } catch { rx = null; }
          if (rx && !rx.test(v)) return msg("bad_pattern", { field: f });
        }
      }
      if (leaf.wire_format && !parseWire(String(v), leaf.wire_format)) {
        if (op.role === "callback") return msg("bad_callback");
        return msg("bad_date", { field: f, format: wireLabel(leaf.wire_format, lang) });
      }
    }
    return null;
  }

  function wireLabel(w, lg) {
    let s = w.replace("%Y", "YYYY").replace("%m", "MM").replace("%d", "DD").replace("%H", "HH").replace("%M", "MM").replace("%S", "SS");
    if (lg === "tr") s = s.replace("MM-DD", "AA-GG").replace("DD.MM", "GG.AA").replace("DD/MM", "GG/AA");
    return s;
  }

  // ---- helpers over the customer and the session
  const fieldOf = (op, role) => (op.fields || {})[role];
  const identityKeys = (cust) => Object.keys(cust.identity || {});
  const allVerified = (cust, s) => identityKeys(cust).length > 0 && identityKeys(cust).every((k) => s.verified[k]);
  const productsOf = (cust) => (Array.isArray(cust.products) ? cust.products : []);
  const findProduct = (cust, pid) => productsOf(cust).find((p) => String(p[PRODUCTS.id]) === String(pid));
  const hasProducts = (cust) => productsOf(cust).length > 0;

  function faultFor(rec, cust, op, nth) {
    const specs = [...(cust.faults || []), ...(rec.faults || [])];
    for (const f of specs) {
      if (!isObj(f)) continue;
      const target = f.op ?? f.tool ?? f.role;
      if (target !== op.name && target !== op.role && target !== op.path) continue;
      const n = Number(f.fail_first_n || 0);
      if (nth <= n || (Array.isArray(f.fail_calls) && f.fail_calls.map(Number).includes(nth))) return f.mode || "http500";
    }
    return null;
  }

  // ---- verify
  function verify(op, cust, s, args) {
    const maxWrong = maxWrongFor(cust);
    const identity = cust.identity || {};
    let pairs;
    const sel = fieldOf(op, "selector");
    if (sel) {
      pairs = [[args[sel], args[fieldOf(op, "answer") || "answer"]]];
    } else {
      const map = op.identity_fields || {};
      pairs = Object.entries(map).filter(([f]) => !empty(args[f])).map(([f, key]) => [key, args[f]]);
      if (!pairs.length) pairs = Object.keys(identity).filter((k) => !empty(args[k])).map((k) => [k, args[k]]);
      if (!pairs.length) return refuse(op, "invalid", msg("no_answer"));
    }
    const left0 = Math.max(0, maxWrong - s.wrong);
    if (s.wrong >= maxWrong) return refuse(op, "locked", msg("locked"), { verified: false, left: 0 });
    const hintValue = op.hint_value || null;
    let anyWrong = false, hint = null;
    const ok = [];
    for (const [field, answerRaw] of pairs) {
      if (field === undefined || field === null || !(String(field) in identity)) return refuse(op, "invalid", msg("unknown_field"), { verified: false, left: left0 });
      const expected = String(identity[field]);
      const answer = answerRaw === undefined || answerRaw === null ? "" : String(answerRaw).trim();
      if (isIsoDate(expected)) {
        const got = isIsoDate(answer) ? answer : (cfg.lenient_dates === false ? null : parseLooseDate(answer));
        if (!got) {
          // "02.14.1986" for 14.02.1986: unreadable as day-month-year, but it is the right date with day and month
          // swapped -> the hint, not counted
          const sw = swapDayMonth(answer);
          if (hintValue && sw && sw === expected) { hint = hintValue; continue; }
          return refuse(op, "invalid", msg("unreadable_date"), { verified: false, left: left0 });
        }
        if (got === expected) { ok.push(field); continue; }
        const [ey, em, ed] = expected.split("-");
        const [ay, am, ad] = got.split("-");
        if (hintValue && ay === ey && am === ed && ad === em) { hint = hintValue; continue; }
        anyWrong = true;
      } else if (/^\d+$/.test(expected) && /^\d+$/.test(answer.replace(/[\s-]/g, "")) && answer.replace(/[\s-]/g, "").length !== expected.length) {
        return refuse(op, "invalid", msg("unreadable"), { verified: false, left: left0 });
      } else if (answer && normAnswer(answer, /\s/.test(expected.trim())) === normAnswer(expected, /\s/.test(expected.trim()))) {
        ok.push(field);
      } else if (/^\d+$/.test(expected) && answer.replace(/[\s-]/g, "") === expected) {
        ok.push(field);
      } else {
        anyWrong = true;
      }
    }
    if (anyWrong) {
      s.wrong += 1;
      const left = Math.max(0, maxWrong - s.wrong);
      if (left === 0) return refuse(op, "locked", msg("too_many_wrong"), { verified: false, left: 0, all: false });
      return okRes(op, { verified: false, left, all: allVerified(cust, s) });
    }
    if (hint) {
      s.hinted += 1;
      for (const f of ok) s.verified[f] = true;
      return okRes(op, { verified: false, left: left0, all: allVerified(cust, s), hint });
    }
    const again = ok.every((f) => s.verified[f]);
    for (const f of ok) s.verified[f] = true;
    if (again) return okRes(op, { verified: true, left: left0 });
    return okRes(op, { verified: true, left: left0, all: allVerified(cust, s) });
  }

  // ---- account read
  function account(op, cust) {
    const roles = {};
    const R = op.response || {};
    if (R.products) roles.products = clone(productsOf(cust));
    const body = respond(op, true, undefined, roles);
    for (const [k, v] of Object.entries(cust.account || {})) {
      if (getPath(body, k) === undefined) setPath(body, k, clone(v));
    }
    return { status: ST.ok, body };
  }

  function dateOf(op, args) {
    const dtf = fieldOf(op, "datetime");
    if (dtf && !empty(args[dtf])) {
      const p = parseWire(String(args[dtf]), (op.request?.[dtf]?.wire_format) || "%Y-%m-%dT%H:%M:%S");
      return p ? { date: p.date, time: p.time } : { date: null, time: null, bad: true };
    }
    const df = fieldOf(op, "date");
    const tf = fieldOf(op, "time");
    let date = null, time = null, bad = false;
    if (df) {
      const w = op.request?.[df]?.wire_format || "%Y-%m-%d";
      const p = parseWire(String(args[df] ?? ""), w);
      if (p && p.date) date = p.date; else bad = true;
    }
    if (tf) {
      const w = op.request?.[tf]?.wire_format || "%H:%M";
      const p = parseWire(String(args[tf] ?? ""), w);
      if (p && p.time) time = p.time; else bad = true;
    }
    return { date, time, bad };
  }

  // ---- writes
  function promise(op, cust, s, args) {
    const pf = fieldOf(op, "product");
    let pid = null, prod = null;
    if (pf && !empty(args[pf])) {
      pid = args[pf];
      if (hasProducts(cust)) {
        prod = findProduct(cust, pid);
        if (!prod) return refuse(op, "unknown_product", msg("unknown_product"));
      }
    } else if (hasProducts(cust) && productsOf(cust).length === 1 && !pf) {
      prod = productsOf(cust)[0];
      pid = prod[PRODUCTS.id] ?? null;
    }
    const af = fieldOf(op, "amount");
    let amount = null;
    if (af) {
      amount = toNumber(args[af]);
      if (amount === null) return refuse(op, "invalid", msg("bad_type", { field: af, type: "number" }));
      const leaf = (op.request || {})[af] || {};
      if (leaf.type === "integer" && !Number.isInteger(amount)) return refuse(op, "invalid", msg("amount_integer", { field: af }));
      if (amount <= 0) return refuse(op, "invalid", msg("amount_positive", { field: af }));
      amount = Math.round((amount / Number(leaf.scale || 1)) * 100) / 100;
    }
    const d = dateOf(op, args);
    if (d.bad || (!d.date && (fieldOf(op, "date") || fieldOf(op, "datetime")))) {
      const f = fieldOf(op, "date") || fieldOf(op, "datetime");
      return refuse(op, "invalid", msg("bad_date", { field: f, format: wireLabel(op.request?.[f]?.wire_format || "%Y-%m-%d", lang) }));
    }
    if (op.reject_past_dates && d.date) {
      // the call's own date (customer variable `now`), never the server clock: simulated calls carry their own day
      const ref = String((cust.variables || {}).now || "").slice(0, 10);
      if (isIsoDate(ref) && d.date < ref) {
        return refuse(op, "invalid", msg("past_date", { field: fieldOf(op, "date") || fieldOf(op, "datetime") }));
      }
    }
    const onePer = op.one_per || (pf ? "product" : "call");
    if (onePer === "product" && pid !== null && s.promises.some((p) => String(p.product_id) === String(pid))) {
      return refuse(op, "conflict", msg("duplicate_promise"));
    }
    if (onePer === "call" && s.promises.length) return refuse(op, "conflict", msg("duplicate_call_promise"));
    const promiseId = (op.id_prefix || "pr") + (s.promises.length + 1);
    const rec = { promise_id: promiseId, product_id: pid, type: prod ? prod[PRODUCTS.type] ?? null : null, amount, date: d.date };
    if (d.time) rec.time = d.time;
    rec.args = clone(args);
    s.promises.push(rec);
    return okRes(op, { pid: promiseId });
  }

  function note(op, cust, s, args) {
    const pf = fieldOf(op, "product");
    const rec = {};
    if (pf && !empty(args[pf])) {
      if (hasProducts(cust) && !findProduct(cust, args[pf])) return refuse(op, "unknown_product", msg("unknown_product"));
      rec.product_id = args[pf];
    }
    const rf = fieldOf(op, "reason");
    rec.reason = rf ? (empty(args[rf]) ? null : args[rf]) : null;
    const tf = fieldOf(op, "text");
    if (tf && !empty(args[tf])) rec.text = args[tf];
    rec.args = clone(args);
    s.notes.push(rec);
    return okRes(op, { pid: (op.id_prefix || "n") + s.notes.length });
  }

  function callback(op, cust, s, args) {
    const d = dateOf(op, args);
    const needDate = !!(fieldOf(op, "date") || fieldOf(op, "datetime"));
    const needTime = !!(fieldOf(op, "time") || fieldOf(op, "datetime"));
    if (d.bad || (needDate && !d.date) || (needTime && !d.time)) return refuse(op, "invalid", msg("bad_callback"));
    const rec = { date: d.date, time: d.time, args: clone(args) };
    s.callbacks.push(rec);
    return okRes(op, { pid: (op.id_prefix || "cb") + s.callbacks.length });
  }

  function transfer(op, cust, s, args) {
    const qf = fieldOf(op, "queue");
    const q = qf ? args[qf] : null;
    if (qf && empty(q)) return refuse(op, "invalid", msg("missing", { field: qf }));
    s.transfers.push({ queue: q ?? null, args: clone(args) });
    return okRes(op, { pid: (op.id_prefix || "tr") + s.transfers.length });
  }

  function close(op, cust, s, args, t) {
    const of = fieldOf(op, "outcome");
    const rf = fieldOf(op, "reason");
    const outcome = of ? args[of] : null;
    if (of && empty(outcome)) return refuse(op, "invalid", msg("missing", { field: of }));
    let reason = rf && !empty(args[rf]) ? args[rf] : null;
    const reasonless = (op.reasonless || []).map(String);
    const table = isObj(op.reasons_by_outcome) ? op.reasons_by_outcome : null;
    if (outcome !== null && reasonless.includes(String(outcome))) {
      reason = null;                                   // promise/paid-like outcomes carry no reason in the ledger
    } else if (rf) {
      const allowed = table && Array.isArray(table[outcome]) ? table[outcome].map(String) : null;
      if (allowed && allowed.length === 0) reason = null;
      else if (reason === null && (op.reason_required !== false)) return refuse(op, "invalid", msg("reason_required", { outcome }));
      else if (allowed && reason !== null && !allowed.includes(String(reason))) {
        return refuse(op, "invalid", msg("reason_not_allowed", { outcome, allowed: allowed.join(", ") }));
      }
    }
    s.outcome = outcome ?? null;
    s.reason = reason;
    s.closed = true;
    s.closed_at_ms = t;
    s.close_args = clone(args);
    return okRes(op, {});
  }

  // ---- one tool call
  async function handleOp(op, params, args, request, env) {
    const cf = op.customer || cfg.customer_field || "customer_id";
    const cidRaw = args[cf] ?? params[cf];
    const cust = empty(cidRaw) ? null : CUST.get(String(cidRaw).trim());
    const isStub = op.role === "stub" || op.stub === true;
    if (!cust) {
      // a stub (a service the contract does not have, or an operation with no role) always answers ok
      if (isStub) return okRes(op, {});
      return { status: ST.unknown_customer, body: respond(op, false, msg("unknown_customer")) };
    }
    const cid = String(cust.customer_id ?? cust.id);
    const key = ledgerKey(cid, sessionKey(op, args, request));
    return withLock(key, async () => {
      const t = now();
      const rec = (await storeGet(env, key)) || { customer_id: cid, current: null, history: [], faults: [] };
      if (!rec.current) rec.current = freshSession(1, t);
      rollover(rec, op.role, t);
      const s = rec.current;
      const name = op.name || op.role;
      const nth = (s.op_counts[name] || 0) + 1;
      s.op_counts[name] = nth;
      s.last_at_ms = t;
      let out;
      if (isStub) {
        (s.stubs = s.stubs || []).push({ op: name, args: clone(args) });
        out = okRes(op, {});
      } else if (s.closed) out = refuse(op, "closed", msg("closed"));
      else {
        const mode = faultFor(rec, cust, op, nth);
        if (mode) {
          s.failures[name] = (s.failures[name] || 0) + 1;
          out = mode === "ok_false" ? refuse(op, "refused", msg("service_failed"))
            : { status: ST.fault, body: respond(op, false, msg("service_failed")) };
        } else if ((op.needs_verified ?? (op.role === "account" || op.role === "promise")) && !allVerified(cust, s)) {
          out = refuse(op, "not_verified", msg("not_verified"));
        } else {
          for (const [src, dst] of Object.entries(op.aliases || {})) {
            if (empty(args[dst]) && !empty(args[src])) args[dst] = args[src];
          }
          const err = validate(op, args);
          if (err) out = refuse(op, "invalid", err);
          else if (op.role === "verify") out = verify(op, cust, s, args);
          else if (op.role === "account") out = account(op, cust);
          else if (op.role === "promise") out = promise(op, cust, s, args);
          else if (op.role === "note") out = note(op, cust, s, args);
          else if (op.role === "callback") out = callback(op, cust, s, args);
          else if (op.role === "transfer") out = transfer(op, cust, s, args);
          else out = close(op, cust, s, args, t);
        }
      }
      s.calls.push({ n: s.calls.length + 1, tool: name, role: op.role, at: new Date(t).toISOString(), args: clone(args),
        status: out.status, result: isObj(out.body) ? clone(out.body) : {} });
      await storePut(env, key, rec);
      return out;
    });
  }

  function publicLedger(rec, cid) {
    const strip = (s) => {
      if (!s) return s;
      const o = clone(s);
      delete o.op_counts;
      o.last_at = new Date(o.last_at_ms || 0).toISOString();
      delete o.last_at_ms;
      o.closed_at = o.closed_at_ms ? new Date(o.closed_at_ms).toISOString() : null;
      delete o.closed_at_ms;
      return o;
    };
    if (!rec) return { customer_id: cid, ...strip(freshSession(0, now())), history: [] };
    return { customer_id: cid, ...strip(rec.current || freshSession(0, now())), faults: rec.faults || [],
      history: (rec.history || []).map(strip) };
  }

  function servedOpenapi(origin) {
    const doc = clone(openapi || {});
    if (isObj(doc)) doc.servers = [{ url: origin }];
    return doc;
  }

  function adminAllowed(request, env) {
    const token = env && env.ADMIN_TOKEN;
    if (!token) return true;
    return request.headers.get("x-admin-token") === token;
  }

  async function fetchImpl(request, env) {
    const url = new URL(request.url);
    const method = request.method.toUpperCase();
    let path = url.pathname.replace(/\/{2,}/g, "/");
    if (path.length > 1) path = path.replace(/\/+$/, "");
    if (method === "OPTIONS") return new Response(null, { status: 204, headers: headers() });
    if (method === "GET" || method === "HEAD") {
      if (path === "/openapi.json") return json(servedOpenapi(url.origin));
      const base = BASES.find((b) => path === b + "/openapi.json");
      if (base) return json(servedOpenapi(url.origin + base));
      if (path === "/health" || path === "/") {
        return json({ ok: true, service: cfg.name || "bank-mock", engine: ENGINE_VERSION, lang,
          customers: CUST.size, operations: OPS.map((o) => ({ name: o.name || o.role, role: o.role,
            method: String(o.method || "POST").toUpperCase(), path: o.path })),
          storage: env && (env.__store || env.LEDGER_DO) ? "durable_object" : env && env.LEDGER ? "kv" : "memory",
          kv: !!(env && env.LEDGER), kv_errors: STATS.kv_errors, kv_last_error: STATS.kv_last_error,
          time: new Date(now()).toISOString() });
      }
      if (path === "/customers") {
        return json({ ok: true, customers: [...CUST.values()].map((c) => ({ customer_id: c.customer_id ?? c.id,
          variables: c.variables || {}, products: productsOf(c).length })) });
      }
      if (path.startsWith("/ledger/")) {
        const cid = safeDecode(path.slice(8));
        const skey = url.searchParams.get("session") || "";
        return json(publicLedger(await storeGet(env, ledgerKey(cid, skey)), cid));
      }
    }
    if ((method === "POST" || method === "DELETE" || method === "GET") && (path === "/reset" || path.startsWith("/reset/"))) {
      if (!adminAllowed(request, env)) return json({ ok: false, error: "admin token required" }, 401);
      if (path === "/reset") {
        if (env.__store) {
          const own = await storeKeys(env, "L:");
          for (const k of own) await storeDel(env, k);
          return json({ ok: true, reset: own.length });
        }
        const keys = await storeKeys(env, "L:");
        for (const c of CUST.keys()) keys.push(ledgerKey(c, ""));
        const uniq = [...new Set(keys)];
        for (const k of uniq) await storeDel(env, k);
        return json({ ok: true, reset: uniq.length });
      }
      const cid = safeDecode(path.slice(7));
      const skey = url.searchParams.get("session") || "";
      await storeDel(env, ledgerKey(cid, skey));
      return json({ ok: true, customer_id: cid });
    }
    if (method === "POST" && path.startsWith("/admin/fault/")) {
      if (!adminAllowed(request, env)) return json({ ok: false, error: "admin token required" }, 401);
      const cid = safeDecode(path.slice(13));
      if (!CUST.has(cid)) return json({ ok: false, error: MSG.unknown_customer }, 404);
      let spec = {};
      try { spec = await request.json(); } catch { return json({ ok: false, error: MSG.body_json }, 400); }
      const key = ledgerKey(cid, url.searchParams.get("session") || "");
      return withLock(key, async () => {
        const rec = (await storeGet(env, key)) || { customer_id: cid, current: null, history: [], faults: [] };
        rec.faults = Array.isArray(spec) ? spec : (isObj(spec) && Object.keys(spec).length ? [...(rec.faults || []), spec] : []);
        await storePut(env, key, rec);
        return json({ ok: true, faults: rec.faults });
      });
    }
    const hit = route(method, path);
    if (!hit) {
      if (method !== "POST" && method !== "GET") return json({ ok: false, error: MSG.method }, 405);
      return json({ ok: false, error: MSG.unknown_operation + " " + path }, ST.unknown_operation);
    }
    let body = {};
    if (method !== "GET" && method !== "HEAD") {
      const text = await request.text();
      if (text.trim()) {
        try { body = JSON.parse(text); } catch {
          return json(respond(hit.op, false, MSG.body_json), 400);
        }
      }
      if (!isObj(body)) body = {};
    }
    const args = { ...Object.fromEntries(url.searchParams.entries()), ...hit.params, ...body };
    const out = await handleOp(hit.op, hit.params, args, request, env);
    return json(out.body, out.status);
  }

  // ---- Durable Object dispatch (the stateless Worker side): every request that reads or writes a customer's
  // ledger goes to that customer's DO; everything else (health, openapi, unknown customer, bad JSON) answers here.
  function stubFor(env, cid) {
    const ns = env.LEDGER_DO;
    return ns.get(ns.idFromName(String(cid)));
  }

  function forward(env, cid, request, method, bodyText) {
    const h = new Headers(request.headers);
    h.delete("content-length");
    const init = { method, headers: h };
    if (bodyText !== undefined && method !== "GET" && method !== "HEAD") init.body = bodyText;
    return stubFor(env, cid).fetch(new Request(request.url, init));
  }

  async function dispatch(request, env) {
    const url = new URL(request.url);
    const method = request.method.toUpperCase();
    let path = url.pathname.replace(/\/{2,}/g, "/");
    if (path.length > 1) path = path.replace(/\/+$/, "");
    const local = (bodyText) => fetchImpl(bodyText === undefined ? request
      : new Request(request.url, { method, headers: request.headers, body: bodyText }), env);
    if (method === "OPTIONS") return local();
    if ((method === "GET" || method === "HEAD") && path.startsWith("/ledger/")) {
      const cid = safeDecode(path.slice(8));
      return CUST.has(cid) ? forward(env, cid, request, method) : local();
    }
    if ((method === "POST" || method === "DELETE" || method === "GET") && (path === "/reset" || path.startsWith("/reset/"))) {
      if (!adminAllowed(request, env)) return json({ ok: false, error: "admin token required" }, 401);
      if (path === "/reset") {
        const outs = await Promise.all([...CUST.keys()].map(async (cid) => {
          const r = await forward(env, cid, request, "POST", "");
          const b = await r.json().catch(() => ({}));
          return { ok: r.ok && b.ok !== false, n: Number(b.reset) || 0 };
        }));
        const bad = outs.filter((o) => !o.ok).length;
        if (bad) return json({ ok: false, error: "reset failed for " + bad + " customer(s)" }, 500);
        return json({ ok: true, reset: CUST.size, keys: outs.reduce((a, o) => a + o.n, 0) });
      }
      const cid = safeDecode(path.slice(7));
      return CUST.has(cid) ? forward(env, cid, request, method) : local();
    }
    if (method === "POST" && path.startsWith("/admin/fault/")) {
      const cid = safeDecode(path.slice(13));
      if (!CUST.has(cid)) return local();
      return forward(env, cid, request, method, await request.text());
    }
    if (method === "GET" || method === "HEAD") {
      if (path === "/openapi.json" || path === "/health" || path === "/" || path === "/customers"
        || BASES.some((b) => path === b + "/openapi.json")) return local();
    }
    const hit = route(method, path);
    if (!hit) return local();
    let bodyText;
    let body = {};
    if (method !== "GET" && method !== "HEAD") {
      bodyText = await request.text();
      if (bodyText.trim()) {
        try { body = JSON.parse(bodyText); } catch { return local(bodyText); }
      }
      if (!isObj(body)) body = {};
    }
    const args = { ...Object.fromEntries(url.searchParams.entries()), ...hit.params, ...body };
    const cf = hit.op.customer || cfg.customer_field || "customer_id";
    const cidRaw = args[cf] ?? hit.params[cf];
    const cust = empty(cidRaw) ? null : CUST.get(String(cidRaw).trim());
    if (!cust) return local(bodyText);
    return forward(env, String(cust.customer_id ?? cust.id), request, method, bodyText);
  }

  return {
    async fetch(request, env) {
      try {
        env = env || {};
        if (env.LEDGER_DO && !env.__store) return await dispatch(request, env);
        return await fetchImpl(request, env);
      } catch (e) {
        return json({ ok: false, error: "service failed: " + String((e && e.message) || e).slice(0, 200) }, 500);
      }
    },
    stats: () => ({ ...STATS }),
  };
}
