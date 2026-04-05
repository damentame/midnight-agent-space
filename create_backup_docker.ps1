# Create a backup from the Docker container's database
# Usage: .\create_backup_docker.ps1 [backup_file_path]

param(
    [string]$BackupFile = ".\backups\midnight_agent_space_dev_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump",
    [string]$CONTAINER_NAME = "pgvector-postgres",
    [string]$DB_NAME = "midnight_agent_space_dev",
    [string]$DB_USER = "postgres"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Create Database Backup from Docker" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if container is running
$containerRunning = docker ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" | Select-String -Pattern $CONTAINER_NAME
if (-not $containerRunning) {
    Write-Host "ERROR: Container $CONTAINER_NAME is not running!" -ForegroundColor Red
    Write-Host "  Please start the container first: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}

# Create backup directory if it doesn't exist
$backupDir = Split-Path $BackupFile -Parent
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

$containerBackupPath = "/tmp/backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump"

Write-Host "Creating backup from container..." -ForegroundColor Yellow
Write-Host "  Container: $CONTAINER_NAME" -ForegroundColor Gray
Write-Host "  Database: $DB_NAME" -ForegroundColor Gray
Write-Host "  Output: $BackupFile" -ForegroundColor Gray
Write-Host ""

# Create the backup inside the container
docker exec $CONTAINER_NAME pg_dump -U $DB_USER -d $DB_NAME -F c -f $containerBackupPath -v 2>&1 | ForEach-Object {
    if ($_ -match "ERROR|error|Error") {
        Write-Host "  $_" -ForegroundColor Red
    } else {
        Write-Host "  $_" -ForegroundColor Gray
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Backup failed!" -ForegroundColor Red
    exit 1
}

# Copy backup file from container to host
Write-Host "Copying backup from container..." -ForegroundColor Yellow
docker cp "${CONTAINER_NAME}:${containerBackupPath}" $BackupFile

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to copy backup from container!" -ForegroundColor Red
    exit 1
}

# Clean up backup file in container
docker exec $CONTAINER_NAME rm -f $containerBackupPath 2>&1 | Out-Null

$fileSize = [math]::Round((Get-Item $BackupFile).Length / 1MB, 2)
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Backup created successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  File: $BackupFile" -ForegroundColor White
Write-Host "  Size: $fileSize MB" -ForegroundColor White
Write-Host ""

# Verify backup contents
Write-Host "Verifying backup contents..." -ForegroundColor Cyan
$backupList = docker exec $CONTAINER_NAME pg_restore -l $containerBackupPath 2>&1
$tableCount = ($backupList | Select-String -Pattern "TABLE DATA" | Measure-Object).Count
$functionCount = ($backupList | Select-String -Pattern "FUNCTION|PROCEDURE" | Measure-Object).Count

Write-Host "  Tables with data: $tableCount" -ForegroundColor $(if ($tableCount -gt 0) { "Green" } else { "Yellow" })
Write-Host "  Functions/Procedures: $functionCount" -ForegroundColor $(if ($functionCount -gt 0) { "Green" } else { "Yellow" })

if ($tableCount -eq 0) {
    Write-Host ""
    Write-Host "WARNING: Backup contains no table data!" -ForegroundColor Yellow
    Write-Host "  This might be normal if your database is empty." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green

