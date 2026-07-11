#!/usr/bin/env bash
# Build the Claude Desktop bundle (investo.mcpb) from manifest.json.
# Requires Node.js (uses `npx @anthropic-ai/mcpb`). Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Validating manifest.json ..."
npx -y @anthropic-ai/mcpb validate manifest.json

echo "Packing investo.mcpb ..."
npx -y @anthropic-ai/mcpb pack . investo.mcpb

echo "Done -> investo.mcpb (drag into Claude Desktop > Settings > Extensions to install)."
