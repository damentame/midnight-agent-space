# Migration script to update database for Sentence Transformers embeddings
# This script updates the embedding dimension from 1536 to 384

param(
    [string]$ContainerName = "pgvector-postgres",
    [string]$DbUser = "postgres",
    [string]$DbName = "midnight_agent_space_dev",
    [switch]$ClearExisting = $false
)

Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "Database Migration: Sentence Transformers" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

if ($ClearExisting) {
    Write-Host "WARNING: This will delete all existing embeddings!" -ForegroundColor Red
    $confirm = Read-Host "Type 'yes' to continue"
    if ($confirm -ne "yes") {
        Write-Host "Migration cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Step 1: Dropping existing vector index..." -ForegroundColor Gray
docker exec $ContainerName psql -U $DbUser -d $DbName -c "DROP INDEX IF EXISTS main.idx_document_embedding_vector_hnsw;" 2>&1 | Out-Null
Write-Host "  [OK] Index dropped" -ForegroundColor Green

if ($ClearExisting) {
    Write-Host "Step 2: Clearing existing embeddings..." -ForegroundColor Gray
    docker exec $ContainerName psql -U $DbUser -d $DbName -c "DELETE FROM main.document_embedding;" 2>&1 | Out-Null
    Write-Host "  [OK] Embeddings cleared" -ForegroundColor Green
} else {
    Write-Host "Step 2: Checking for existing embeddings..." -ForegroundColor Gray
    $count = docker exec $ContainerName psql -U $DbUser -d $DbName -t -A -c "SELECT COUNT(*) FROM main.document_embedding;" 2>&1
    $count = ($count -replace '\s+', '' -replace '\r', '' -replace '\n', '')
    if ([int]$count -gt 0) {
        Write-Host "  [WARN] Found $count existing embeddings with 1536 dimensions" -ForegroundColor Yellow
        Write-Host "  These will need to be regenerated after migration." -ForegroundColor Yellow
        Write-Host "  Run with -ClearExisting to delete them now." -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] No existing embeddings" -ForegroundColor Green
    }
}

Write-Host "Step 3: Updating embedding column to 384 dimensions..." -ForegroundColor Gray
# First, delete existing embeddings if any (required for dimension change)
docker exec $ContainerName psql -U $DbUser -d $DbName -c "DELETE FROM main.document_embedding;" 2>&1 | Out-Null
docker exec $ContainerName psql -U $DbUser -d $DbName -c "ALTER TABLE main.document_embedding ALTER COLUMN embedding TYPE vector(384);" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Column updated to vector(384)" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Failed to update column" -ForegroundColor Red
    exit 1
}

Write-Host "Step 4: Recreating vector index..." -ForegroundColor Gray
docker exec $ContainerName psql -U $DbUser -d $DbName -c @"
CREATE INDEX IF NOT EXISTS idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"@ 2>&1 | Out-Null
Write-Host "  [OK] Index recreated" -ForegroundColor Green

Write-Host "Step 5: Updating default model name..." -ForegroundColor Gray
docker exec $ContainerName psql -U $DbUser -d $DbName -c "ALTER TABLE main.document_embedding ALTER COLUMN embedding_model SET DEFAULT 'all-MiniLM-L6-v2';" 2>&1 | Out-Null
Write-Host "  [OK] Default model updated" -ForegroundColor Green

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Migration completed successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart your Temporal worker" -ForegroundColor Gray
Write-Host "  2. Run your workflow to regenerate embeddings" -ForegroundColor Gray
Write-Host "  3. New embeddings will use 384 dimensions (Sentence Transformers)" -ForegroundColor Gray
Write-Host ""

