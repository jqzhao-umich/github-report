#!/bin/bash
# Production deployment script
# This script deploys the application in production mode

set -e

echo "Starting GitHub Report App in PRODUCTION mode..."

# Ensure .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Please create a .env file with required environment variables:"
    echo "  GITHUB_TOKEN=..."
    echo "  GITHUB_ORG_NAME=..."
    echo "  GITHUB_ITERATION_START=..."
    echo "  GITHUB_ITERATION_END=..."
    echo "  GITHUB_ITERATION_NAME=..."
    exit 1
fi

# Build and start with production overrides
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo ""
echo "✅ Production deployment complete!"
echo "📊 Dashboard: http://localhost:8000/github-report"
echo ""
echo "View logs: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f"
echo "Stop: docker compose -f docker-compose.yml -f docker-compose.prod.yml down"
