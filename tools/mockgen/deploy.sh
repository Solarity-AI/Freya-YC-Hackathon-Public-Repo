#!/usr/bin/env bash
# Deploy the bank mock (mock/) to Cloudflare Workers and check /health.
#
#   tools/mockgen/deploy.sh                    real deploy: wrangler deploy (ledger = Durable Object class Ledger,
#                                              SQLite-backed, from wrangler.toml; needs Workers Paid). A legacy
#                                              wrangler.toml without a Durable Object binding gets a KV namespace.
#   tools/mockgen/deploy.sh --name my-mock     set the Worker name first (the URL becomes my-mock.<sub>.workers.dev)
#   tools/mockgen/deploy.sh --temporary        rehearsal without a Cloudflare login: wrangler dev --local + a free
#                                              Quick Tunnel (https://<random>.trycloudflare.com). Runs in the
#                                              foreground; the URL dies with the process. Never for the final.
#   tools/mockgen/deploy.sh --dry-run          bundle only (wrangler deploy --dry-run), no upload
#   tools/mockgen/deploy.sh --dir path/to/mock another mock folder
#
# Needs: node + npx (wrangler 4 is fetched by npx), `npx wrangler login` once for a real deploy.
# Prints MOCK_URL=<url> on success (real deploy) and exits non-zero when /health does not answer ok.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$HERE/../../mock"
MODE=deploy
NAME=""
PORT=8787
while [ $# -gt 0 ]; do
  case "$1" in
    --temporary) MODE=temporary ;;
    --dry-run) MODE=dry ;;
    --name) NAME="$2"; shift ;;
    --dir) DIR="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

export WRANGLER_SEND_METRICS=false
WR=(npx --yes wrangler@4)
cd "$DIR"

for f in config.json customers.json openapi.json src/worker.js src/engine.js wrangler.toml; do
  [ -f "$f" ] || { echo "missing $DIR/$f (run tools/mockgen/make_config.py first)" >&2; exit 2; }
done
python3 - <<'EOF'
import json, sys
for f in ("config.json", "customers.json", "openapi.json"):
    try:
        json.load(open(f, encoding="utf-8"))
    except Exception as e:
        sys.exit(f"{f}: not valid JSON ({e})")
c = json.load(open("customers.json", encoding="utf-8"))
print(f"data ok: {len(json.load(open('config.json'))['ops'])} operations, {len(c)} customers")
EOF

if [ -n "$NAME" ]; then
  python3 - "$NAME" <<'EOF'
import re, sys
p = "wrangler.toml"
s = open(p).read()
s = re.sub(r'(?m)^name\s*=.*$', 'name = "%s"' % sys.argv[1], s, count=1)
open(p, "w").write(s)
EOF
fi

if [ "$MODE" = dry ]; then
  "${WR[@]}" deploy --dry-run --outdir "${TMPDIR:-/tmp}/bank-mock-build"
  exit 0
fi

if [ "$MODE" = temporary ]; then
  echo "temporary mock: wrangler dev --local on :$PORT behind a Quick Tunnel (look for the trycloudflare.com URL)"
  exec "${WR[@]}" dev --local --port "$PORT" --tunnel
fi

# ---- real deploy: the ledger is a Durable Object (no KV needed); KV namespace only for a legacy wrangler.toml
if grep -q '^\[\[durable_objects.bindings\]\]' wrangler.toml; then
  echo "ledger storage: Durable Object (LEDGER_DO, class Ledger); no KV namespace needed"
elif ! grep -q '^\[\[kv_namespaces\]\]' wrangler.toml; then
  echo "creating KV namespace LEDGER"
  OUT="$("${WR[@]}" kv namespace create LEDGER 2>&1 || true)"
  echo "$OUT" | tail -5
  ID="$(echo "$OUT" | grep -oE '[0-9a-f]{32}' | head -1 || true)"
  if [ -z "$ID" ]; then
    # already exists: find it in the list
    ID="$("${WR[@]}" kv namespace list 2>/dev/null | python3 -c '
import json, sys
txt = sys.stdin.read()
try:
    rows = json.loads(txt[txt.index("["):])
except Exception:
    rows = []
hits = [r["id"] for r in rows if "LEDGER" in r.get("title", "")]
print(hits[0] if hits else "")')"
  fi
  if [ -z "$ID" ]; then
    echo "could not create or find the LEDGER namespace (is wrangler logged in? npx wrangler login)" >&2
    exit 1
  fi
  printf '\n[[kv_namespaces]]\nbinding = "LEDGER"\nid = "%s"\n' "$ID" >> wrangler.toml
  echo "KV namespace LEDGER id=$ID written to wrangler.toml"
fi

LOG="$(mktemp)"
"${WR[@]}" deploy 2>&1 | tee "$LOG"
URL="$(grep -oE 'https://[A-Za-z0-9.-]+\.workers\.dev' "$LOG" | head -1 || true)"
rm -f "$LOG"
if [ -z "$URL" ]; then
  echo "deploy printed no workers.dev URL" >&2
  exit 1
fi
for i in 1 2 3 4 5 6; do
  if BODY="$(curl -fsS -m 10 "$URL/health")"; then
    echo "$BODY" | head -c 400; echo
    echo "MOCK_URL=$URL"
    exit 0
  fi
  sleep 5
done
echo "health check failed at $URL/health" >&2
exit 1
