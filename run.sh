#!/usr/bin/env bash
# Script de automatización para FinSight
set -euo pipefail

# 1. Verificar si existe el archivo .env
if [ ! -f .env ]; then
    echo "Error: No se encontró el archivo .env en la raíz."
    echo "Copiando desde env.example... Por favor, edítalo con tus llaves antes de volver a ejecutar."
    cp env.example .env
    exit 1
fi

# 2. Levantar los servicios con Docker Compose
echo "Iniciando FinSight con Docker Compose..."
docker compose up --build
