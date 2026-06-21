# MAS end-to-end smoke script (dry-run by default; set E2E_LIVE=1 for full agent execute)
param(
  [string]$ApiBase = "http://127.0.0.1:8001",
  [int]$ProjectId = 5
)

$ErrorActionPreference = "Stop"

function Invoke-MasGet($path) {
  return Invoke-RestMethod -Uri "$ApiBase$path" -Method Get
}

function Invoke-MasPost($path, $body = @{}) {
  return Invoke-RestMethod -Uri "$ApiBase$path" -Method Post -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 8)
}

Write-Host "MAS E2E smoke - API $ApiBase project $ProjectId"

$health = Invoke-MasGet "/health"
if ($health.status -ne "healthy") { throw "API health check failed: $($health | ConvertTo-Json -Compress)" }
Write-Host "OK health"

$project = Invoke-MasGet "/api/projects/$ProjectId"
Write-Host "OK project: $($project.project_name)"

$summary = Invoke-MasGet "/api/projects/$ProjectId/summary"
Write-Host "OK summary: $($summary.counts.documents) docs / $($summary.counts.tasks) tasks"

$projectHealth = Invoke-MasGet "/api/projects/$ProjectId/health"
Write-Host "OK project health runnable=$($projectHealth.runnable.ok)"

$preview = Invoke-MasGet "/api/projects/$ProjectId/preview/detect"
if ($preview.ok) {
  if ($preview.preview_url -match ":5173") { throw "Preview must not use port 5173" }
  Write-Host "OK preview detect: $($preview.preview_url) framework=$($preview.framework)"
} else {
  Write-Host "WARN preview detect: $($preview.error)"
}

$compact = Invoke-MasGet "/api/projects/$ProjectId/context-pack/compact"
if ($compact.figma_import_count -gt 0) {
  if (-not $compact.has_figma_excerpt) { throw "Figma import present but compact excerpt is empty" }
  if (-not $compact.design_context_required) { throw "Figma import should set design_context_required" }
  Write-Host "OK figma context: $($compact.figma_import_count) import(s), excerpt present"
} else {
  Write-Host "WARN no figma_import documents in context pack"
}

if ($env:E2E_LIVE -eq "1") {
  Write-Host "E2E_LIVE=1 - starting quick run (requires Cursor Agent)"
  $run = Invoke-MasPost "/api/projects/$ProjectId/quick-runs" @{
    user_prompt = "Continue MorningGlory implementation from serialized tasks."
    runtime_provider = "cursor-agent"
    template_name = "executor"
  }
  Write-Host "Started run #$($run.agent_run_id)"
} else {
  Write-Host "Dry-run complete (set E2E_LIVE=1 to execute live agent run)"
}
