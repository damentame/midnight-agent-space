#!/bin/bash
# Restore database from backup and then apply new schema objects
# Usage: ./restore_database.sh [backup_file_path]

set -e

# Default backup file (change this to your actual backup file)
BACKUP_FILE="${1:-./backups/midnight_agent_space_dev.dump}"
DB_NAME="midnight_agent_space_dev"
DB_USER="postgres"
CONTAINER_NAME="pgvector-postgres"

echo "=========================================="
echo "Database Restore and Schema Update Script"
echo "=========================================="
echo ""

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    echo "Available backup files:"
    ls -la backups/*.dump 2>/dev/null || echo "  No backup files found in backups/ directory"
    exit 1
fi

echo "Step 1: Dropping existing database..."
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"

echo "Step 2: Creating fresh database..."
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

echo "Step 3: Enabling pgvector extension..."
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "Step 4: Restoring from backup file: $BACKUP_FILE"
docker exec -i $CONTAINER_NAME pg_restore -U $DB_USER -d $DB_NAME --verbose --no-owner --no-acl < "$BACKUP_FILE"

if [ $? -ne 0 ]; then
    echo "ERROR: Restore failed!"
    exit 1
fi

echo "Step 5: Applying new schema objects (vector tables)..."
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME < temporal/schema/vector_tables.sql

echo "Step 6: Applying new schema objects (functions and procedures)..."
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME < temporal/schema/create_functions.sql

echo ""
echo "=========================================="
echo "Restore and schema update complete!"
echo "=========================================="
echo ""
echo "Verifying objects..."
echo ""
echo "Tables in public schema:"
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "\dt public.*"

echo ""
echo "Functions and procedures in public schema:"
docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -c "\df public.*"

echo ""
echo "Done!"

