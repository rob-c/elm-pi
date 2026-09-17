#!/usr/bin/env bash
# Start the ELM tool-call shim. Reads ELM_BASE_URL / SHIM_PORT / SHIM_MODELS.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/shim.py"
