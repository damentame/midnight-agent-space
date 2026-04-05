# Restore database from backup and then apply new schema objects
# Usage: .\restore_database.ps1 [backup_file_path]

param(
    [string]$BackupFile = ".\backups\midnight_agent_space_dev_fixed.dump"
)

$ErrorActionPreference = "Stop"

$DB_NAME = "midnight_agent_space_dev"
$DB_USER = "postgres"
$CONTAINER_NAME = "pgvector-postgres"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Database Restore and Schema Update Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if backup file exists
if (-not (Test-Path $BackupFile)) {
    Write-Host "ERROR: Backup file not found: $BackupFile" -ForegroundColor Red
    Write-Host "Available backup files:" -ForegroundColor Yellow
    Get-ChildItem -Path "backups\*.dump" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $($_.FullName)" }
    exit 1
}

Write-Host "Step 1: Dropping existing database..." -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"

Write-Host "Step 2: Creating fresh database..." -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

Write-Host "Step 3: Enabling pgvector extension..." -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;"

Write-Host "Step 4: Restoring from backup file: $BackupFile" -ForegroundColor Yellow
Write-Host "  Backup file size: $([math]::Round((Get-Item $BackupFile).Length / 1MB, 2)) MB" -ForegroundColor Gray
Write-Host "  Using backup file: $BackupFile" -ForegroundColor Gray

# Copy backup file into container for more reliable restore
$containerBackupPath = "/tmp/restore_backup.dump"
Write-Host "  Copying backup file into container..." -ForegroundColor Gray
docker cp $BackupFile "${CONTAINER_NAME}:${containerBackupPath}"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to copy backup file into container!" -ForegroundColor Red
    exit 1
}

# Check backup file format by reading first few bytes
$backupHeader = docker exec $CONTAINER_NAME head -c 4 $containerBackupPath | Format-Hex | Select-Object -ExpandProperty Bytes | Select-Object -First 4

if ($backupHeader[0] -eq 0x50 -and $backupHeader[1] -eq 0x47 -and $backupHeader[2] -eq 0x44 -and $backupHeader[3] -eq 0x4D) {
    Write-Host "  Detected PostgreSQL custom format dump" -ForegroundColor Gray
    Write-Host "  Running pg_restore with verbose output..." -ForegroundColor Gray
    
    # First, let's see what's in the backup
    Write-Host "  Checking backup contents..." -ForegroundColor Gray
    $backupList = docker exec $CONTAINER_NAME pg_restore -l $containerBackupPath 2>&1
    $tableCount = ($backupList | Select-String -Pattern "TABLE DATA|TABLE" | Measure-Object).Count
    Write-Host "    Found $tableCount table definitions in backup" -ForegroundColor $(if ($tableCount -gt 0) { "Green" } else { "Yellow" })
    
    if ($tableCount -eq 0) {
        Write-Host "  WARNING: Backup file appears to contain no tables!" -ForegroundColor Yellow
        Write-Host "  Showing backup contents:" -ForegroundColor Yellow
        $backupList | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    }
    
    # Use pg_restore for custom format - show verbose output
    Write-Host "  Restoring..." -ForegroundColor Gray
    
    # Capture output - pg_restore writes to stderr, so we need to handle it properly
    $restoreOutput = @()
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $rawOutput = docker exec $CONTAINER_NAME pg_restore -U $DB_USER -d $DB_NAME --verbose --no-owner --no-acl $containerBackupPath 2>&1
        $restoreExitCode = $LASTEXITCODE
        
        # Convert all output to strings
        if ($rawOutput) {
            $restoreOutput = $rawOutput | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                } else {
                    $_.ToString()
                }
            }
        }
    } catch {
        # If we catch an exception, it's likely just stderr output being treated as error
        $restoreOutput = @($_.Exception.Message)
        $restoreExitCode = $LASTEXITCODE
        if ($restoreExitCode -eq 0) {
            # If exit code is 0, assume it's just stderr output, not a real error
            $restoreExitCode = 0
        }
    } finally {
        $ErrorActionPreference = 'Stop'
    }
    
    # Show all restore output to see what's happening
    $restoreItems = 0
    $restoreOutput | ForEach-Object {
        $line = $_.ToString()
        if ($line -match "ERROR|error|Error|FATAL|fatal") {
            Write-Host "  $line" -ForegroundColor Red
        } elseif ($line -match "WARNING|warning") {
            Write-Host "  $line" -ForegroundColor Yellow
        } elseif ($line -match "processing|restoring|TABLE|SEQUENCE|FUNCTION|PROCEDURE") {
            Write-Host "  $line" -ForegroundColor Cyan
            $restoreItems++
        } elseif ($line -match "connecting") {
            # Suppress connection messages
        } else {
            Write-Host "  $line" -ForegroundColor Gray
        }
    }
    
    Write-Host "  Restored $restoreItems items" -ForegroundColor $(if ($restoreItems -gt 0) { "Green" } else { "Yellow" })
    
    if ($restoreExitCode -ne 0) {
        Write-Host "  WARNING: pg_restore had issues (exit code: $restoreExitCode)" -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] Restore completed" -ForegroundColor Green
    }
} else {
    Write-Host "  Detected SQL format dump" -ForegroundColor Gray
    Write-Host "  Running psql..." -ForegroundColor Gray
    # Use psql for SQL format
    $restoreOutput = @()
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $rawOutput = docker exec $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f $containerBackupPath 2>&1
        $restoreExitCode = $LASTEXITCODE
        
        # Convert all output to strings
        if ($rawOutput) {
            $restoreOutput = $rawOutput | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                } else {
                    $_.ToString()
                }
            }
        }
    } catch {
        $restoreOutput = @($_.Exception.Message)
        $restoreExitCode = $LASTEXITCODE
        if ($restoreExitCode -eq 0) {
            $restoreExitCode = 0
        }
    } finally {
        $ErrorActionPreference = 'Stop'
    }
    
    # Filter and display output
    $restoreOutput | ForEach-Object {
        $line = $_.ToString()
        if ($line -match "ERROR|error|Error|FATAL|fatal") {
            Write-Host "  $line" -ForegroundColor Red
        } elseif ($line -match "WARNING|warning") {
            Write-Host "  $line" -ForegroundColor Yellow
        } else {
            Write-Host "  $line" -ForegroundColor Gray
        }
    }
    
    if ($restoreExitCode -ne 0) {
        Write-Host "  WARNING: psql restore had issues (exit code: $restoreExitCode)" -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] Restore completed" -ForegroundColor Green
    }
}

# Clean up backup file from container
docker exec $CONTAINER_NAME rm -f $containerBackupPath 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Restore may have had errors (exit code: $LASTEXITCODE)" -ForegroundColor Yellow
    Write-Host "  Continuing anyway to check what was restored..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 4a: Verifying restore..." -ForegroundColor Yellow
Start-Sleep -Seconds 2  # Give restore a moment to complete

# Check tables in main schema (where backup restores to)
$tableCountResult = docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -t -A -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'main';"
$tableCount = [int]($tableCountResult -replace '\s+', '' -replace '\r', '' -replace '\n', '')

# Also check public schema
$publicTableCountResult = docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -t -A -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public';"
$publicTableCount = [int]($publicTableCountResult -replace '\s+', '' -replace '\r', '' -replace '\n', '')

$totalTables = $tableCount + $publicTableCount
Write-Host "  Tables in main schema: $tableCount" -ForegroundColor $(if ($tableCount -gt 0) { "Green" } else { "Yellow" })
Write-Host "  Tables in public schema: $publicTableCount" -ForegroundColor $(if ($publicTableCount -gt 0) { "Green" } else { "Gray" })
Write-Host "  Total tables: $totalTables" -ForegroundColor $(if ($totalTables -gt 0) { "Green" } else { "Red" })

if ($totalTables -eq 0) {
    Write-Host "ERROR: No tables were restored from backup!" -ForegroundColor Red
    Write-Host "  This suggests the backup restore failed or the backup file is empty/corrupted." -ForegroundColor Yellow
    Write-Host "  Please check:" -ForegroundColor Yellow
    Write-Host "    1. Is the backup file valid?" -ForegroundColor Yellow
    Write-Host "    2. Does it contain data?" -ForegroundColor Yellow
    Write-Host "    3. Check the restore output above for errors" -ForegroundColor Yellow
    exit 1
}

Write-Host "Step 5: Applying new schema objects (vector tables in main schema)..." -ForegroundColor Yellow
Get-Content "temporal\schema\vector_tables.sql" | docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME

Write-Host "Step 6: Applying new schema objects (functions and procedures in main schema)..." -ForegroundColor Yellow
Get-Content "temporal\schema\create_functions.sql" | docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Restore and schema update complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Verifying objects..." -ForegroundColor Cyan
Write-Host ""
Write-Host "All tables by schema:" -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "SELECT schemaname, COUNT(*) as table_count FROM pg_tables WHERE schemaname IN ('public', 'main') GROUP BY schemaname ORDER BY schemaname;"

Write-Host ""
Write-Host "Tables in public schema:" -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "\dt public.*" | Select-Object -First 20

Write-Host ""
Write-Host "Tables in main schema:" -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "\dt main.*"

Write-Host ""
Write-Host "Functions and procedures in main schema:" -ForegroundColor Yellow
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "\df main.*"

Write-Host ""
Write-Host "Done!" -ForegroundColor Green

