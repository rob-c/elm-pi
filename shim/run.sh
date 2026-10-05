#!/usr/bin/env bash
# Start the ELM tool-call shim. Reads ELM_BASE_URL / SHIM_PORT / SHIM_MODELS.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ELM_PI_PYTHON is exported by the launcher and bootstrap.sh; see lib/sandbox.sh.
exec "${ELM_PI_PYTHON:-python3}" -E -S "$HERE/shim.py"
