#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Installing @openai/codex and @anthropic-ai/claude-code..."
npm install

echo ""
node ./scripts/verify-agent-clis.js

echo ""
echo "Add these to temporal/.env or .env if the dashboard cannot find the CLIs on PATH:"
echo "  CODEX_COMMAND=$ROOT/node_modules/.bin/codex"
echo "  CLAUDE_COMMAND=$ROOT/node_modules/.bin/claude"
