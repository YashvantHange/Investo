# Build the Claude Desktop bundle (investo.mcpb) from manifest.json.
# Requires Node.js (uses `npx @anthropic-ai/mcpb`). Run from the repo root.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Validating manifest.json ..."
npx -y "@anthropic-ai/mcpb" validate manifest.json

Write-Host "Packing investo.mcpb ..."
npx -y "@anthropic-ai/mcpb" pack . investo.mcpb

Write-Host "Done -> investo.mcpb (drag into Claude Desktop > Settings > Extensions to install)."
