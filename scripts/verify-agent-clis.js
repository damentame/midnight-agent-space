#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const localBin = path.join(root, "node_modules", ".bin");

function resolveCommand(name) {
  const extension = process.platform === "win32" ? ".cmd" : "";
  const localPath = path.join(localBin, `${name}${extension}`);
  return localPath;
}

function check(label, command, versionArgs) {
  const result = spawnSync(command, versionArgs, {
    encoding: "utf8",
    shell: process.platform === "win32",
  });
  const ok = result.status === 0;
  const version = (result.stdout || result.stderr || "").trim().split("\n")[0];
  console.log(`${ok ? "[ok]" : "[missing]"} ${label}: ${version || result.error || "not available"}`);
  return ok;
}

const codex = resolveCommand("codex");
const claude = resolveCommand("claude");

const codexOk = check("Codex CLI", codex, ["--version"]);
const claudeOk = check("Claude CLI", claude, ["-v"]);

const cursorAgent =
  process.platform === "win32"
    ? process.env.CURSOR_AGENT_COMMAND || "cursor-agent.cmd"
    : process.env.CURSOR_AGENT_COMMAND || "cursor-agent";
const cursorOk = check("Cursor Agent", cursorAgent, ["--version"]);

if (!codexOk || !claudeOk) {
  console.log("\nInstall or refresh CLIs with: npm run setup:clis");
  process.exit(1);
}

console.log("\nCodex and Claude CLIs are available from node_modules/.bin.");
if (!cursorOk) {
  console.log("Cursor Agent was not detected (optional for balanced code routing).");
}
console.log("Optional .env overrides:");
console.log(`  CODEX_COMMAND=${codex}`);
console.log(`  CLAUDE_COMMAND=${claude}`);
console.log(`  CURSOR_AGENT_COMMAND=${cursorAgent}`);
