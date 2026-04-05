# Complete refresh script: Cleanup + Restore
# This script does a full cleanup and then restores the database
# Usage: .\refresh_all.ps1 [-BackupFile path] [-Force] [-KeepVolumes]

param(
    [string]$BackupFile = ".\backups\midnight_agent_space_dev.dump",
    [switch]$Force,
    [switch]$KeepVolumes
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Complete Refresh Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Clean up all Docker containers and volumes" -ForegroundColor Yellow
Write-Host "  2. Start fresh containers" -ForegroundColor Yellow
Write-Host "  3. Restore database from backup" -ForegroundColor Yellow
Write-Host "  4. Apply new schema objects" -ForegroundColor Yellow
Write-Host ""

if (-not $Force) {
    $confirmation = Read-Host "Are you sure you want to continue? (yes/no)"
    if ($confirmation -ne "yes") {
        Write-Host "Refresh cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Phase 1: Cleanup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
& ".\cleanup_docker.ps1" -Force:$Force -KeepVolumes:$KeepVolumes

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Phase 2: Starting Containers" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "Starting main postgres container..." -ForegroundColor Yellow
docker-compose up -d
Start-Sleep -Seconds 3

Write-Host "Starting temporal containers..." -ForegroundColor Yellow
Set-Location temporal
docker-compose -f docker-compose.temporal.yml up -d
Set-Location ..
Start-Sleep -Seconds 5

Write-Host "Waiting for containers to be ready..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$ready = $false

while ($attempt -lt $maxAttempts -and -not $ready) {
    $status = docker exec pgvector-postgres pg_isready -U postgres 2>$null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        Write-Host "  [OK] PostgreSQL is ready" -ForegroundColor Green
    } else {
        $attempt++
        Write-Host "  Waiting for PostgreSQL... ($attempt/$maxAttempts)" -ForegroundColor Gray
        Start-Sleep -Seconds 1
    }
}

if (-not $ready) {
    Write-Host "ERROR: PostgreSQL did not become ready in time!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Phase 3: Restoring Database" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
& ".\restore_database.ps1" -BackupFile $BackupFile

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Complete Refresh Finished!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your environment is now fresh and ready to test!" -ForegroundColor Cyan
Write-Host ""

