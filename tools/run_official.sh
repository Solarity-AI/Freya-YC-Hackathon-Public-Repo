#!/usr/bin/env bash
# Official kit simulation (simulated customer + judge + ledger). One at a time per workspace.
# usage: tools/run_official.sh <slot> <A|B> [extra run_cases args, e.g. --reps 3 --only PUB-04]
set -euo pipefail
cd "$(dirname "$0")/.."
slot="$1"; brief="$2"; shift 2
agent=$(python3 -c "import json;print(json.load(open('state/$slot.json'))['$slot']['agent_id'])")
set -a; source ../kit/build-the-builder/env.sh; set +a
mkdir -p results/official
out="results/official/$slot-$brief-$(date -u +%Y%m%dT%H%M%SZ).json"
cd kit && PYTHONUNBUFFERED=1 python3 tools/run_cases.py "$agent" --brief "$brief" --out "../$out" "$@"
