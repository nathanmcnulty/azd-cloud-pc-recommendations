#!/usr/bin/env sh
set -eu

if ! command -v pwsh >/dev/null 2>&1; then
  echo "PowerShell 7 (pwsh) is required for the azd pre-provision hook." >&2
  exit 1
fi

exec pwsh -NoProfile -File "$(dirname "$0")/preprovision.ps1"
