#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${FC_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  if [[ -x "$repo_dir/betting-machine-fc/venv/bin/python" ]]; then
    python_bin="$repo_dir/betting-machine-fc/venv/bin/python"
  else
    python_bin="$(command -v python3 || true)"
  fi
fi
if [[ -z "$python_bin" || ! -x "$python_bin" ]]; then
  echo "Could not find FC Python. Set FC_PYTHON or install betting-machine-fc/venv." >&2
  exit 1
fi
if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab is not installed; configure a systemd timer or install cron first." >&2
  exit 1
fi

entry="*/5 * * * * cd '$repo_dir' && '$python_bin' '$repo_dir/scripts/fc-settle-live.py' >> /tmp/fc-settle-live.log 2>&1 # fc-settle-live"
current="$(crontab -l 2>/dev/null || true)"
updated="$(printf '%s\n' "$current" | sed '\|# fc-settle-live$|d')"
{
  [[ -z "$updated" ]] || printf '%s\n' "$updated"
  printf '%s\n' "$entry"
} | crontab -

echo "Installed FC settlement cron for every 5 minutes."
echo "Repo: $repo_dir"
echo "Python: $python_bin"
echo "Log: /tmp/fc-settle-live.log"
echo "The job uses a process lock shared with API-triggered settlement."
