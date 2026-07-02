#!/usr/bin/env bash
# Inject a file.requested via core-backend /analyze and trace the job across every
# worker (core-backend -> ml-layer -> sandbox -> llm -> verdict) by pulling each
# one's log line for the job_id.
#
# Run ON GPE-NYX (kubectl configured + NodePort 30080 local), or from a
# VPN-reachable host with:  BACKEND=http://172.16.249.133:30080 ./inject-and-trace.sh ...
#
# Usage: scripts/inject-and-trace.sh <file> [sender] [subject]
#   e.g. scripts/inject-and-trace.sh apps/workers/ml_layer/data/malicious/<sha>
set -euo pipefail

FILE="${1:?usage: inject-and-trace.sh <file> [sender] [subject]}"
SENDER="${2:-attacker@evil.example}"
SUBJECT="${3:-Invoice overdue - please review}"
BACKEND="${BACKEND:-http://localhost:30080}"
TOKEN="${TOKEN:-dev}"
WAIT="${WAIT:-9}"

b() { printf '\033[1m%s\033[0m\n' "$*"; }
sect() { printf '\n\033[1;36m── %s ──────────────────────────\033[0m\n' "$*"; }

b "==> POST ${BACKEND}/api/v1/analyze   (file: ${FILE})"
RESP=$(curl -s -X POST "${BACKEND}/api/v1/analyze" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${FILE}" -F "sender=${SENDER}" -F "subject=${SUBJECT}" \
  -F "body_text=please review the attached invoice")
JOB=$(printf '%s' "$RESP" | sed -n 's/.*"job_id":"\([^"]*\)".*/\1/p')
[ -n "$JOB" ] || { echo "!! no job_id in response: $RESP"; exit 1; }
b "    job_id = ${JOB}"
b "==> letting the pipeline run (${WAIT}s)..."
sleep "$WAIT"

# $1=namespace  $2=deployment
trace() {
  local out
  out=$(kubectl -n "$1" logs "deploy/$2" --tail=400 2>/dev/null | grep -F "$JOB" || true)
  if [ -n "$out" ]; then printf '%s\n' "$out"; else echo "  (no log line for this job)"; fi
}

sect "core-backend  · ingress + verdict consumer"
trace pipeline core-backend
sect "ml-layer      · static PDF analysis -> ml_layer.result"
trace pipeline ml-layer
sect "sandbox       · detonation dispatch (sandbox namespace)"
trace sandbox  sandbox-consumer
sect "llm-layer     · semantic analyst (only if verdict=needs_more_context)"
trace pipeline llm-layer
sect "verdict-layer · aggregation -> verdict.result"
trace pipeline verdict-layer

VERDICT=$(kubectl -n pipeline logs deploy/verdict-layer --tail=400 2>/dev/null \
  | grep -F "$JOB" | grep -oE 'blocked|allowed|warning' | tail -1 || true)
printf '\n\033[1;32m==> FINAL VERDICT: %s\033[0m\n' "${VERDICT:-<none yet — ML<=90 & terminal sandbox verdict may still be resolving; re-run trace or check the reaper>}"
