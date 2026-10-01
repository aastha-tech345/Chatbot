#!/usr/bin/env bash
# Run this file as a shell script: ./build-production.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_FRONTEND_DIR="$ROOT_DIR/backend/frontend_dist"

if [ ! -f "$FRONTEND_DIR/.env.production" ]; then
  echo "Missing frontend/.env.production"
  echo "Create it from frontend/.env.example and set NEXT_PUBLIC_API_BASE_URL for production."
  exit 1
fi

set -a
# shellcheck disable=SC1091
. "$FRONTEND_DIR/.env.production"
set +a

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  npm ci --prefix "$FRONTEND_DIR"
fi

npm run build --prefix "$FRONTEND_DIR"

rm -rf "$BACKEND_FRONTEND_DIR"
mkdir -p "$BACKEND_FRONTEND_DIR"
cp -R "$FRONTEND_DIR/out/." "$BACKEND_FRONTEND_DIR/"

echo "Frontend production build copied to backend/frontend_dist"
