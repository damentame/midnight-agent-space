#!/bin/bash
# Cleanup script to refresh Docker containers and volumes
# Usage: ./cleanup_docker.sh [--force] [--keep-volumes]

set -e

FORCE=false
KEEP_VOLUMES=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --keep-volumes)
            KEEP_VOLUMES=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--force] [--keep-volumes]"
            exit 1
            ;;
    esac
done

# Containers to clean up
CONTAINERS=(
    "pgvector-postgres"
    "temporal-server"
    "temporal-ui"
    "temporal-postgres"
)

# Volumes to clean up
VOLUMES=(
    "midnightagentspace_pgvector_data"
    "midnightagentspace_temporal-postgres-data"
    "pgvector_data"
)

echo "=========================================="
echo "Docker Cleanup Script"
echo "=========================================="
echo ""

if [ "$FORCE" != true ]; then
    echo "This will:"
    echo "  - Stop and remove containers: ${CONTAINERS[*]}"
    if [ "$KEEP_VOLUMES" != true ]; then
        echo "  - Remove volumes: ${VOLUMES[*]}"
    else
        echo "  - Keep volumes (data will be preserved)"
    fi
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirmation
    if [ "$confirmation" != "yes" ]; then
        echo "Cleanup cancelled."
        exit 0
    fi
fi

echo ""
echo "Step 1: Stopping containers..."
for container in "${CONTAINERS[@]}"; do
    if docker ps -a --format "{{.Names}}" | grep -q "^${container}$"; then
        echo "  Stopping $container..."
        docker stop "$container" 2>/dev/null && echo "    ✓ Stopped $container" || echo "    ⊘ Could not stop $container"
    else
        echo "  ⊘ $container not found"
    fi
done

echo ""
echo "Step 2: Removing containers..."
for container in "${CONTAINERS[@]}"; do
    if docker ps -a --format "{{.Names}}" | grep -q "^${container}$"; then
        echo "  Removing $container..."
        docker rm "$container" 2>/dev/null && echo "    ✓ Removed $container" || echo "    ⊘ Could not remove $container"
    fi
done

if [ "$KEEP_VOLUMES" != true ]; then
    echo ""
    echo "Step 3: Removing volumes..."
    for volume in "${VOLUMES[@]}"; do
        if docker volume ls --format "{{.Name}}" | grep -q "^${volume}$"; then
            echo "  Removing volume $volume..."
            docker volume rm "$volume" 2>/dev/null && echo "    ✓ Removed volume $volume" || echo "    ⊘ Could not remove volume $volume (may be in use)"
        else
            echo "  ⊘ Volume $volume not found"
        fi
    done
else
    echo ""
    echo "Step 3: Skipping volume removal (--keep-volumes specified)"
fi

echo ""
echo "Step 4: Cleaning up Docker Compose resources..."

# Clean up main docker-compose
if [ -f "docker-compose.yml" ]; then
    echo "  Cleaning up main docker-compose..."
    docker-compose down -v 2>/dev/null && echo "    ✓ Cleaned up main docker-compose" || echo "    ⊘ Could not clean up main docker-compose"
fi

# Clean up temporal docker-compose
if [ -f "temporal/docker-compose.temporal.yml" ]; then
    echo "  Cleaning up temporal docker-compose..."
    (cd temporal && docker-compose -f docker-compose.temporal.yml down -v 2>/dev/null) && echo "    ✓ Cleaned up temporal docker-compose" || echo "    ⊘ Could not clean up temporal docker-compose"
fi

echo ""
echo "Step 5: Pruning unused Docker resources..."
docker system prune -f 2>/dev/null
echo "  ✓ Pruned unused Docker resources"

echo ""
echo "=========================================="
echo "Cleanup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Start containers: docker-compose up -d"
echo "  2. Start temporal: cd temporal && docker-compose -f docker-compose.temporal.yml up -d"
echo "  3. Restore database: ./restore_database.sh"
echo ""

