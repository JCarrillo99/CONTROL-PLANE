#!/bin/bash
# Script para configurar el entorno virtual del CLI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "🔧 Configurando entorno virtual para el CLI..."

# Crear venv si no existe
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv "$VENV_DIR"
fi

# Activar venv e instalar dependencias
echo "📥 Instalando dependencias..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "✅ Entorno virtual configurado correctamente"
echo ""
echo "Para usar el CLI:"
echo "  ./server-cli sync"
echo "  sudo ./server-cli create"
echo ""
echo "O activa el venv manualmente:"
echo "  source venv/bin/activate"
echo "  python3 cli.py sync"
