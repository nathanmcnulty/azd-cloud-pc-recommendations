#!/usr/bin/env sh
set -eu

if ! command -v pwsh >/dev/null 2>&1; then
  echo "PowerShell 7 (pwsh) is required for the azd post-provision hook." >&2
  exit 1
fi

exec pwsh -NoProfile -File "$(dirname "$0")/postprovision.ps1"
