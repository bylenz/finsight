#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "No .env found — copying from env.example. Edit it before continuing."
    cp env.example .env
fi

docker compose up --build "$@"
