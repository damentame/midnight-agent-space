# Install Codex CLI and Claude CLI for Midnight Agent Space.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing @openai/codex and @anthropic-ai/claude-code..."
npm install

Write-Host ""
node .\scripts\verify-agent-clis.js

Write-Host ""
Write-Host "Add these to temporal/.env or .env if the dashboard cannot find the CLIs on PATH:"
Write-Host "  CODEX_COMMAND=$Root\node_modules\.bin\codex.cmd"
Write-Host "  CLAUDE_COMMAND=$Root\node_modules\.bin\claude.cmd"
