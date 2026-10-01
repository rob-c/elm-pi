#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

npm audit --audit-level=high --package-lock-only --no-fund

AUDIT_DIR="$(mktemp -d)"
trap 'rm -rf "$AUDIT_DIR"' EXIT
cp templates/packages.json "$AUDIT_DIR/package.json"
cp templates/packages-lock.json "$AUDIT_DIR/package-lock.json"
(cd "$AUDIT_DIR" && npm audit --audit-level=high --package-lock-only --no-fund)
