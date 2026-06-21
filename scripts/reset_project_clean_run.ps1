# Full project reset: refresh runs/worktrees, wipe documents, re-import Figma, regenerate tasks.
param(
  [string]$ApiBase = "http://127.0.0.1:8001",
  [int]$ProjectId = 5,
  [string]$FigmaUrl = "https://www.figma.com/design/Gum6FrRjiBVkT6FJiGssPj/Midnight-UI?node-id=1026-19507",
  [string]$FigmaToken = "",
  [string]$Goal = "Implement the Morning Glory Coffee Co app to match the linked Figma design exactly."
)

$ErrorActionPreference = "Stop"

function Invoke-MasGet($path) {
  return Invoke-RestMethod -Uri "$ApiBase$path" -Method Get
}

function Invoke-MasPost($path, $body = @{}) {
  return Invoke-RestMethod -Uri "$ApiBase$path" -Method Post -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 8)
}

if (-not $FigmaToken) {
  $FigmaToken = $env:FIGMA_ACCESS_TOKEN
}
if (-not $FigmaToken) {
  $FigmaToken = $env:FIGMA_API_TOKEN
}

Write-Host "MAS clean reset - project $ProjectId"

$health = Invoke-MasGet "/health"
if ($health.status -ne "healthy") { throw "API not healthy" }
Write-Host "OK API health"

$refresh = Invoke-MasPost "/api/projects/$ProjectId/refresh" @{
  reason = "Clean reset for Figma-fidelity re-run"
  created_by = "reset_project_clean_run.ps1"
}
Write-Host "OK refresh: runs/tasks/worktrees reset"

$docs = Invoke-MasGet "/api/projects/$ProjectId/documents"
$docIds = @()
if ($docs -is [array]) {
  $docIds = $docs | ForEach-Object { $_.document_id }
} elseif ($docs.documents) {
  $docIds = $docs.documents | ForEach-Object { $_.document_id }
}
if ($docIds.Count -gt 0) {
  Invoke-MasPost "/api/projects/$ProjectId/documents/batch-delete" @{ document_ids = $docIds } | Out-Null
  Write-Host "OK deleted $($docIds.Count) documents"
} else {
  Write-Host "OK no documents to delete"
}

$resolvedFigmaUrl = $FigmaUrl.Trim()
if (-not $resolvedFigmaUrl) {
  try {
    $metaResp = Invoke-MasGet "/api/projects/$ProjectId/health"
    $figmaSource = $metaResp.metadata.figma_source
    if ($figmaSource -and $figmaSource.url) {
      $resolvedFigmaUrl = $figmaSource.url
    }
  } catch {
    # health may not expose metadata on older builds
  }
}
if (-not $resolvedFigmaUrl) {
  throw "FigmaUrl is required (or store figma_source in project metadata). Pass -FigmaUrl with node-id."
}
if (-not $FigmaToken) {
  throw "Figma token required: set FIGMA_ACCESS_TOKEN or pass -FigmaToken"
}

$importBody = @{
  url = $resolvedFigmaUrl
  token = $FigmaToken
  notes = "Binding design reference for clean re-run. Match layout, typography, colors, and components exactly."
}
$import = Invoke-MasPost "/api/projects/$ProjectId/figma/import" $importBody
Write-Host "OK figma import: $($import.document_name) exports=$($import.image_document_ids.Count)"
if ($import.warnings) {
  foreach ($w in $import.warnings) { Write-Host "WARN figma: $w" }
}

$health = Invoke-MasGet "/api/projects/$ProjectId/health"
$repoPath = $health.repo_path
if (-not $repoPath) { $repoPath = $health.runnable.repo_path }

$plan = Invoke-MasPost "/api/projects/$ProjectId/analysis-plan" @{
  goal = $Goal
  repo_path = $repoPath
}
Write-Host "OK analysis plan: $($plan.tasks.Count) tasks (includes serialize)"

$compact = Invoke-MasGet "/api/projects/$ProjectId/context-pack/compact"
if ($compact.figma_import_count -lt 1) { throw "Expected figma_import after re-import" }
if (-not $compact.has_figma_excerpt) { throw "Figma excerpt missing from compact context pack" }
Write-Host "OK context pack: figma excerpt present, design_context_required=$($compact.design_context_required)"

$preview = Invoke-MasGet "/api/projects/$ProjectId/preview/detect"
if ($preview.ok) {
  Write-Host "OK preview detect: $($preview.preview_url) framework=$($preview.framework)"
} else {
  Write-Host "WARN preview detect: $($preview.error)"
}

$tasks = Invoke-MasGet "/api/projects/$ProjectId/tasks"
Write-Host "Ready for clean execute on project $ProjectId ($($tasks.Count) tasks QUEUED)"
Write-Host "Open http://127.0.0.1:5173/projects/$ProjectId/execute and click Execute."
