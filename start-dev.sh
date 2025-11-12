#!/bin/bash
# Development environment startup script
# This script sets up environment variables and starts the containers

set -e

# Export current user's UID and GID for Docker
export USER_ID=$(id -u)
export GROUP_ID=$(id -g)
export USERNAME=$(whoami)

echo "Starting GitHub Report App in DEVELOPMENT mode..."
echo "Using UID: $USER_ID, GID: $GROUP_ID, User: $USERNAME"

# Build and start containers
docker compose down
docker compose build --build-arg USER_ID=$USER_ID --build-arg GROUP_ID=$GROUP_ID --build-arg USERNAME=$USERNAME
docker compose up -d

echo ""
echo "✅ Application started!"
echo "📊 Dashboard: http://localhost:8000/github-report"
echo "📝 API Docs: http://localhost:8000/docs"
echo ""
echo "View logs: docker compose logs -f"
echo "Stop: docker compose down"
