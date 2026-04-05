# Script to properly restart the Temporal worker
# This ensures the connection pool is recreated with the correct schema settings

Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "Restarting Temporal Worker" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

Write-Host "Step 1: Checking if worker is running..." -ForegroundColor Gray
$workerProcess = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*worker.py*" }
if ($workerProcess) {
    Write-Host "  Found running worker process (PID: $($workerProcess.Id))" -ForegroundColor Yellow
    Write-Host "  Please stop it manually with Ctrl+C, then press Enter to continue..." -ForegroundColor Yellow
    Read-Host
} else {
    Write-Host "  [OK] No worker process found" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 2: Verifying database tables exist..." -ForegroundColor Gray
$tableCheck = docker exec pgvector-postgres psql -U postgres -d midnight_agent_space_dev -t -A -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'main' AND tablename IN ('document_chunk', 'document_embedding');" 2>&1
$tableCount = ($tableCheck -replace '\s+', '' -replace '\r', '' -replace '\n', '')
if ($tableCount -eq "2") {
    Write-Host "  [OK] Both tables exist in main schema" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Tables may not exist (found $tableCount tables)" -ForegroundColor Yellow
    Write-Host "  Run: docker exec -i pgvector-postgres psql -U postgres -d midnight_agent_space_dev < temporal\schema\vector_tables.sql" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 3: Starting worker..." -ForegroundColor Gray
Write-Host "  Navigate to temporal directory and run: python worker.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Ready to start worker!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

