# Create a backup of your local PostgreSQL database
# Usage: .\create_backup.ps1 [backup_file_path]

param(
    [string]$BackupFile = ".\backups\midnight_agent_space_dev_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump",
    [string]$DB_HOST = "localhost",
    [int]$DB_PORT = 5432,
    [string]$DB_NAME = "midnight_agent_space_dev",
    [string]$DB_USER = "postgres"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Create Database Backup Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if pg_dump is available
try {
    $pgDumpVersion = pg_dump --version 2>&1
    Write-Host "Found: $pgDumpVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: pg_dump not found!" -ForegroundColor Red
    Write-Host "  Please install PostgreSQL client tools or use Docker to create backup" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternative: Use Docker to create backup:" -ForegroundColor Yellow
    Write-Host "  docker exec pgvector-postgres pg_dump -U postgres -F c -f /backups/backup.dump midnight_agent_space_dev" -ForegroundColor White
    exit 1
}

# Prompt for password
$DB_PASSWORD = Read-Host "Enter database password (or press Enter if no password)" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($DB_PASSWORD)
$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

# Set PGPASSWORD environment variable
$env:PGPASSWORD = $plainPassword

Write-Host ""
Write-Host "Creating backup..." -ForegroundColor Yellow
Write-Host "  Database: $DB_NAME" -ForegroundColor Gray
Write-Host "  Host: $DB_HOST`:$DB_PORT" -ForegroundColor Gray
Write-Host "  Output: $BackupFile" -ForegroundColor Gray
Write-Host ""

# Create backup directory if it doesn't exist
$backupDir = Split-Path $BackupFile -Parent
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

# Create the backup
pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -F c -f $BackupFile -v

if ($LASTEXITCODE -eq 0) {
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
    $backupList = pg_restore -l $BackupFile 2>&1
    $tableCount = ($backupList | Select-String -Pattern "TABLE DATA" | Measure-Object).Count
    $functionCount = ($backupList | Select-String -Pattern "FUNCTION|PROCEDURE" | Measure-Object).Count
    
    Write-Host "  Tables with data: $tableCount" -ForegroundColor $(if ($tableCount -gt 0) { "Green" } else { "Yellow" })
    Write-Host "  Functions/Procedures: $functionCount" -ForegroundColor $(if ($functionCount -gt 0) { "Green" } else { "Yellow" })
    
    if ($tableCount -eq 0) {
        Write-Host ""
        Write-Host "WARNING: Backup contains no table data!" -ForegroundColor Yellow
        Write-Host "  This might be normal if your database is empty." -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "ERROR: Backup failed!" -ForegroundColor Red
    exit 1
}

# Clear password from environment
$env:PGPASSWORD = ""

Write-Host ""
Write-Host "Done!" -ForegroundColor Green

