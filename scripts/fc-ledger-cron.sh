#!/usr/bin/env bash
# fc-ledger-cron.sh — log all scan projections, grade the due ones, refresh
# the committed model-performance report. Read-only toward the ROI pipeline:
# never touches picks.json, bets.db, or tracker_snapshot.json.
#
# Run AFTER (or on the same cadence as) the FC scan so every scan's
# projections land in the ledger. Suggested crontab on the server repo user:
#
#   */30 * * * * /home/ubuntu/mlb-project/scripts/fc-ledger-cron.sh >> /var/log/fc-ledger-cron.log 2>&1
#
# The refreshed reports/fc-model-performance.{json,md} is committed separately
# (deploy/scan chore), never by this script.
#
# Windows dev equivalent via Task Scheduler (every 30 minutes):
#   schtasks /create /tn "FC Ledger Cron" /sc MINUTE /mo 30 \
#     /tr "powershell -File C:\path\to\repo\scripts\fc-ledger-cron.ps1"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ -x betting-machine-fc/venv/bin/python ]; then
  PY=betting-machine-fc/venv/bin/python
else
  PY=python3
fi
echo "[ledger-cron] $(date -u +%FT%TZ) log projections"
"$PY" scripts/fc-log-projections.py
echo "[ledger-cron] $(date -u +%FT%TZ) grade + report"
"$PY" scripts/fc-grade-projections.py --report-out reports/fc-model-performance.json
echo "[ledger-cron] $(date -u +%FT%TZ) done"
