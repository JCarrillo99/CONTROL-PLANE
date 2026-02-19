"""
Punto de entrada: python -m lsxtool

Delega al Control Plane ATLAS (misma app que atlas.cli.app).
"""
import sys
from pathlib import Path

# Asegurar proyecto raíz en path (igual que cli.py)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from atlas.cli.app import app

if __name__ == "__main__":
    app()
