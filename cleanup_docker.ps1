# Cleanup script to refresh Docker containers and volumes
# Usage: .\cleanup_docker.ps1 [-Force] [-KeepVolumes]

param(
    [switch]$Force,
    [switch]$KeepVolumes
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Docker Cleanup Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Containers to clean up
$CONTAINERS = @(
    "pgvector-postgres",
    "temporal-server",
    "temporal-ui",
    "temporal-postgres"
)

# Volumes to clean up
$VOLUMES = @(
    "midnightagentspace_pgvector_data",
    "midnightagentspace_temporal-postgres-data",
    "pgvector_data"
)

if (-not $Force) {
    Write-Host "This will:" -ForegroundColor Yellow
    Write-Host "  - Stop and remove containers: $($CONTAINERS -join ', ')" -ForegroundColor Yellow
    if (-not $KeepVolumes) {
        Write-Host "  - Remove volumes: $($VOLUMES -join ', ')" -ForegroundColor Yellow
    } else {
        Write-Host "  - Keep volumes (data will be preserved)" -ForegroundColor Green
    }
    Write-Host ""
    $confirmation = Read-Host "Are you sure you want to continue? (yes/no)"
    if ($confirmation -ne "yes") {
        Write-Host "Cleanup cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host ""
Write-Host "Step 1: Stopping containers..." -ForegroundColor Yellow
foreach ($container in $CONTAINERS) {
    $exists = docker ps -a --filter "name=$container" --format "{{.Names}}" | Select-String -Pattern $container
    if ($exists) {
        Write-Host "  Stopping $container..." -ForegroundColor Gray
        docker stop $container 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] Stopped $container" -ForegroundColor Green
        }
    } else {
        Write-Host "  [SKIP] $container not found" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Step 2: Removing containers..." -ForegroundColor Yellow
foreach ($container in $CONTAINERS) {
    $exists = docker ps -a --filter "name=$container" --format "{{.Names}}" | Select-String -Pattern $container
    if ($exists) {
        Write-Host "  Removing $container..." -ForegroundColor Gray
        docker rm $container 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] Removed $container" -ForegroundColor Green
        }
    }
}

if (-not $KeepVolumes) {
    Write-Host ""
    Write-Host "Step 3: Removing volumes..." -ForegroundColor Yellow
    foreach ($volume in $VOLUMES) {
        $exists = docker volume ls --filter "name=$volume" --format "{{.Name}}" | Select-String -Pattern $volume
        if ($exists) {
            Write-Host "  Removing volume $volume..." -ForegroundColor Gray
            docker volume rm $volume 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "    [OK] Removed volume $volume" -ForegroundColor Green
            } else {
                Write-Host "    [WARN] Could not remove volume $volume (may be in use)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  [SKIP] Volume $volume not found" -ForegroundColor Gray
        }
    }
} else {
    Write-Host ""
    Write-Host "Step 3: Skipping volume removal (--KeepVolumes specified)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 4: Cleaning up Docker Compose resources..." -ForegroundColor Yellow

# Clean up main docker-compose
if (Test-Path "docker-compose.yml") {
    Write-Host "  Cleaning up main docker-compose..." -ForegroundColor Gray
    $oldErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        docker-compose down -v 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] Cleaned up main docker-compose" -ForegroundColor Green
        }
    } catch {
        # Ignore errors from docker-compose informational messages
    } finally {
        $ErrorActionPreference = $oldErrorAction
    }
}

# Clean up temporal docker-compose
if (Test-Path "temporal\docker-compose.temporal.yml") {
    Write-Host "  Cleaning up temporal docker-compose..." -ForegroundColor Gray
    $oldErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        Set-Location temporal
        docker-compose -f docker-compose.temporal.yml down -v 2>&1 | Out-Null
        Set-Location ..
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] Cleaned up temporal docker-compose" -ForegroundColor Green
        }
    } catch {
        # Ignore errors from docker-compose informational messages
    } finally {
        $ErrorActionPreference = $oldErrorAction
        Set-Location $PSScriptRoot
    }
}

Write-Host ""
Write-Host "Step 5: Pruning unused Docker resources..." -ForegroundColor Yellow
$oldErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
try {
    docker system prune -f 2>&1 | Out-Null
    Write-Host "  [OK] Pruned unused Docker resources" -ForegroundColor Green
} catch {
    # Ignore errors from docker system prune informational messages
} finally {
    $ErrorActionPreference = $oldErrorAction
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Cleanup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Start containers: docker-compose up -d" -ForegroundColor White
Write-Host "  2. Start temporal: cd temporal && docker-compose -f docker-compose.temporal.yml up -d" -ForegroundColor White
Write-Host "  3. Restore database: .\restore_database.ps1" -ForegroundColor White
Write-Host ""

