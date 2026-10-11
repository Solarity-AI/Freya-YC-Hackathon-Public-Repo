"""Smoke-test a running bank mock (deployed Worker, wrangler dev, or `node tools/mockgen/harness.mjs serve`).

    python3 tools/mockgen/smoke.py https://bank-mock.<sub>.workers.dev [--dir mock] [--customer ID | --all]

One call per customer, built from the mock's own config.json + customers.json: reset -> health -> openapi -> the
account read is refused before verification -> every identity answer verifies -> account read -> one promise (a second
one is refused) -> close -> a call after close is refused -> the ledger holds the promise and the outcome -> reset.
Prints one line per check and exits 1 on any failure. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
USER_AGENT = "Mozilla/5.0 (compatible; freya-builder/1.0)"   # Cloudflare answers 403 / error 1010 to Python-urllib


def http(base, method, path, body=None, timeout=15):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method,
                                 headers={"content-type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else None
        except ValueError:
            return e.code, raw


def _get(obj, path):
    cur = obj
    for p in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _wire(date, wire):
    return date.strftime(wire or "%Y-%m-%d")


def run(base, config, customer, log=print):
    ops = {o["role"]: o for o in config["ops"]}
    cf = config.get("customer_field") or "customer_id"
    cid = customer["customer_id"]
    fails = []

    def check(name, cond, detail=""):
        log(("PASS " if cond else "FAIL ") + f"[{cid}] {name}" + ("" if cond else f"  {detail}"))
        if not cond:
            fails.append(name)
        return cond

    def call(role, extra):
        op = ops[role]
        body = {op.get("customer") or cf: cid, **extra}
        return http(base, op["method"] if op["method"] != "GET" else "POST", op["path"], body)

    def ok_of(role, status, body):
        s = (ops[role].get("response") or {}).get("s")
        if s:
            want = (ops[role].get("s_values") or {}).get("ok", True)
            return status < 300 and _get(body, s) == want
        err = (ops[role].get("response") or {}).get("err") or "error"
        return status < 300 and not _get(body or {}, err)

    st, _ = http(base, "POST", f"/reset/{cid}")
    check("reset", st == 200, st)
    st, h = http(base, "GET", "/health")
    check("health", st == 200 and isinstance(h, dict) and h.get("ok") is True, h)
    st, doc = http(base, "GET", "/openapi.json")
    check("openapi.json served", st == 200 and isinstance(doc, dict) and bool(doc.get("paths")), st)
    if "account" in ops:
        st, b = call("account", {})
        check("account refused before verification", not ok_of("account", st, b), b)
    v = ops.get("verify")
    if v:
        fields = v["fields"]
        if fields.get("selector"):
            last = None
            for key, ans in customer["identity"].items():
                st, last = call("verify", {fields["selector"]: key, fields["answer"]: ans})
                check(f"verify {key}", ok_of("verify", st, last) and _get(last, v["response"].get("verified", "verified")) is not False, last)
            if v["response"].get("all"):
                check("all verified", _get(last, v["response"]["all"]) is True, last)
        else:
            inv = {key: f for f, key in (v.get("identity_fields") or {}).items()}
            body = {inv.get(k, k): a for k, a in customer["identity"].items()}
            st, b = call("verify", body)
            check("verify (all fields)", ok_of("verify", st, b), b)
    if "account" in ops:
        st, b = call("account", {})
        check("account read", ok_of("account", st, b), b)
    p = ops.get("promise")
    pid_field = (config.get("products") or {}).get("id") or "product_id"
    if p:
        f = p["fields"]
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        body = {}
        if f.get("product") and customer.get("products"):
            body[f["product"]] = customer["products"][0][pid_field]
        if f.get("amount"):
            body[f["amount"]] = 1 if (p["request"].get(f["amount"], {}).get("type") == "integer") else 1.5
        if f.get("date"):
            body[f["date"]] = _wire(tomorrow, p["request"].get(f["date"], {}).get("wire_format"))
        if f.get("datetime"):
            body[f["datetime"]] = tomorrow.isoformat() + "T12:00:00"
        if f.get("time"):
            body[f["time"]] = "12:00"
        for name, rule in (p.get("request") or {}).items():          # e.g. a required promise-kind enum
            if name not in body and name != f.get("customer") and rule.get("required") and rule.get("enum"):
                body[name] = rule["enum"][0]
        # a customer whose data injects a promise fault (fail_first_n): those first calls must fail, then it works
        n_fault = sum(int(f.get("fail_first_n") or 0) for f in customer.get("faults") or []
                      if isinstance(f, dict) and (f.get("op") or f.get("tool") or f.get("role"))
                      in (p.get("name"), "promise", p.get("path")))
        for i in range(n_fault):
            st, b = call("promise", body)
            check(f"injected promise fault {i + 1}/{n_fault}", not ok_of("promise", st, b), b)
        st, b = call("promise", body)
        check("promise recorded", ok_of("promise", st, b), b)
        st, b = call("promise", body)
        check("second promise refused", not ok_of("promise", st, b), b)
    c = ops.get("close")
    if c:
        f = c["fields"]
        outcomes = c["request"].get(f.get("outcome", ""), {}).get("enum") or ["done"]
        reasonless = c.get("reasonless") or []
        outcome = reasonless[0] if reasonless else outcomes[0]
        body = {f["outcome"]: outcome}
        if f.get("reason") and outcome not in reasonless:
            table = (c.get("reasons_by_outcome") or {}).get(outcome)
            enum = c["request"].get(f["reason"], {}).get("enum") or []
            body[f["reason"]] = (table or enum or ["smoke"])[0]
        st, b = call("close", body)
        check("close", ok_of("close", st, b), b)
        st, b = call("close", body)
        check("call after close refused", not ok_of("close", st, b), b)
    st, led = http(base, "GET", f"/ledger/{cid}")
    check("ledger", st == 200 and isinstance(led, dict), st)
    if p and isinstance(led, dict):
        check("ledger holds one promise", len(led.get("promises") or []) == 1, led.get("promises"))
    if c and isinstance(led, dict):
        check("ledger holds the outcome", led.get("closed") is True and led.get("outcome") is not None, led.get("outcome"))
    st, _ = http(base, "POST", f"/reset/{cid}")
    check("reset after", st == 200, st)
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--dir", default=str(ROOT / "mock"))
    ap.add_argument("--customer", default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir)
    config = json.loads((d / "config.json").read_text())
    customers = json.loads((d / "customers.json").read_text())
    if a.customer:
        customers = [c for c in customers if c["customer_id"] == a.customer]
    elif not a.all:
        customers = customers[:1]
    if not customers:
        print("no customer to test")
        return 1
    fails = []
    for c in customers:
        fails += run(a.url, config, c)
    print(f"{'OK' if not fails else 'FAILED'}: {len(customers)} customer(s), {len(fails)} failed check(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
