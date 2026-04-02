#!/usr/bin/env bash
# Corre toda la Fase 1 de recolección de datos
# Uso: bash run_phase1.sh
# Requiere: GITHUB_TOKEN seteado en el entorno

set -e

VENV=".venv"
if [ ! -d "$VENV" ]; then
    echo "ERROR: .venv no encontrado. Corre: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

source "$VENV/bin/activate"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: GITHUB_TOKEN no seteado. Corre: export GITHUB_TOKEN=ghp_..."
    exit 1
fi

mkdir -p data/raw

echo "=============================="
echo " Fase 1: Recolección de datos "
echo "=============================="

echo ""
echo "[1/4] Aiken stdlib..."
python3 scrape_aiken_stdlib.py

echo ""
echo "[2/4] Aiken docs..."
python3 scrape_aiken_docs.py

echo ""
echo "[3/4] Hydra docs..."
python3 scrape_hydra_docs.py

echo ""
echo "[4/4] GitHub (CIPs + Design Patterns + Hydra code)..."
python3 scrape_github.py

echo ""
echo "=============================="
echo " Fase 1 completa!"
echo "=============================="
echo ""
echo "Archivos generados:"
ls -lh data/raw/
