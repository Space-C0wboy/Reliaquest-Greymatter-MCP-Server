#!/usr/bin/env bash
set -euo pipefail
./.venv/bin/python -m greymatter_mcp.server "$@"
