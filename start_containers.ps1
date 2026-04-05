# Start Docker containers and optionally restore database
# Usage: .\start_containers.ps1 [-Restore] [-BackupFile path]

param(
    [switch]$Restore,
    [string]$BackupFile = ".\backups\midnight_agent_space_dev.dump"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Start Containers Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if containers are already running
$pgRunning = docker ps --filter "name=pgvector-postgres" --format "{{.Names}}" | Select-String -Pattern "pgvector-postgres"
$temporalRunning = docker ps --filter "name=temporal-server" --format "{{.Names}}" | Select-String -Pattern "temporal-server"

if ($pgRunning -or $temporalRunning) {
    Write-Host "Some containers are already running:" -ForegroundColor Yellow
    if ($pgRunning) { Write-Host "  - pgvector-postgres" -ForegroundColor Gray }
    if ($temporalRunning) { Write-Host "  - temporal-server" -ForegroundColor Gray }
    Write-Host ""
    $confirmation = Read-Host "Do you want to stop and restart them? (yes/no)"
    if ($confirmation -eq "yes") {
        Write-Host "Stopping existing containers..." -ForegroundColor Yellow
        if ($pgRunning) { docker stop pgvector-postgres 2>&1 | Out-Null }
        if ($temporalRunning) { 
            docker stop temporal-server temporal-ui temporal-postgres 2>&1 | Out-Null 
        }
        Start-Sleep -Seconds 2
    } else {
        Write-Host "Keeping existing containers running." -ForegroundColor Green
        if ($Restore) {
            Write-Host ""
            Write-Host "Restoring database on existing containers..." -ForegroundColor Yellow
            & ".\restore_database.ps1" -BackupFile $BackupFile
        }
        exit 0
    }
}

Write-Host ""
Write-Host "Step 1: Starting main postgres container..." -ForegroundColor Yellow
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start postgres container!" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Postgres container started" -ForegroundColor Green

Write-Host ""
Write-Host "Step 2: Starting temporal containers..." -ForegroundColor Yellow
Set-Location temporal
docker-compose -f docker-compose.temporal.yml up -d
Set-Location ..
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start temporal containers!" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Temporal containers started" -ForegroundColor Green

Write-Host ""
Write-Host "Step 3: Waiting for containers to be ready..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$pgReady = $false
$temporalReady = $false

# Wait for PostgreSQL
while ($attempt -lt $maxAttempts -and -not $pgReady) {
    $status = docker exec pgvector-postgres pg_isready -U postgres 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $pgReady = $true
        Write-Host "  [OK] PostgreSQL is ready" -ForegroundColor Green
    } else {
        $attempt++
        Write-Host "  Waiting for PostgreSQL... ($attempt/$maxAttempts)" -ForegroundColor Gray
        Start-Sleep -Seconds 1
    }
}

if (-not $pgReady) {
    Write-Host "ERROR: PostgreSQL did not become ready in time!" -ForegroundColor Red
    exit 1
}

# Ensure temporal_visibility database exists
Write-Host "  Ensuring temporal_visibility database exists..." -ForegroundColor Gray
$dbExists = docker exec temporal-postgres psql -U postgres -t -A -c "SELECT 1 FROM pg_database WHERE datname = 'temporal_visibility';" 2>&1
$dbExists = $dbExists -replace '\s+', '' -replace '\r', '' -replace '\n', ''
if ($dbExists -ne "1") {
    docker exec temporal-postgres psql -U postgres -c "CREATE DATABASE temporal_visibility;" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [OK] Created temporal_visibility database" -ForegroundColor Green
    } else {
        Write-Host "    [WARN] Could not create temporal_visibility database (may already exist)" -ForegroundColor Yellow
    }
} else {
    Write-Host "    [OK] temporal_visibility database exists" -ForegroundColor Green
}

# Wait for Temporal (check if port is accessible)
$attempt = 0
while ($attempt -lt $maxAttempts -and -not $temporalReady) {
    try {
        $response = Test-NetConnection -ComputerName localhost -Port 7233 -WarningAction SilentlyContinue -InformationLevel Quiet
        if ($response) {
            $temporalReady = $true
            Write-Host "  [OK] Temporal server is ready" -ForegroundColor Green
        } else {
            $attempt++
            Start-Sleep -Seconds 1
        }
    } catch {
        $attempt++
        Start-Sleep -Seconds 1
    }
}

if (-not $temporalReady) {
    Write-Host "  [WARN] Temporal server may not be ready yet (continuing anyway)" -ForegroundColor Yellow
}

if ($Restore) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "Step 4: Restoring Database" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    & ".\restore_database.ps1" -BackupFile $BackupFile
} else {
    Write-Host ""
    Write-Host "Step 4: Skipping database restore (use -Restore to restore)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Containers Started Successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Services:" -ForegroundColor Cyan
Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor White
Write-Host "  - Temporal Server: localhost:7233" -ForegroundColor White
Write-Host "  - Temporal UI: http://localhost:8080" -ForegroundColor White
Write-Host ""

