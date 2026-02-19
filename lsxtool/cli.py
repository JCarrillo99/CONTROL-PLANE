#!/usr/bin/env python3
"""
LSX Tool - CLI Corporativa Unificada (wiring hacia ATLAS).

Este archivo es un WRAPPER: configura entorno (path, .env, sudo) y delega
la aplicación CLI al Control Plane ATLAS. No contiene lógica de negocio.
"""

import sys
import os
from pathlib import Path

# Proyecto donde vive este CLI (para cargar .env y rutas)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent  # lsxtool/ -> proyecto

# Cargar .env del proyecto PRIMERO para que LSXTOOL_DEV=1 aplique antes de cualquier import
try:
    from dotenv import load_dotenv
    _env_file = _PROJECT_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except Exception:
    pass

# Detectar si estamos ejecutando con sudo y ajustar sys.path si es necesario
if os.geteuid() == 0:
    original_user = os.environ.get('SUDO_USER')
    if original_user:
        original_home = Path(f"/home/{original_user}")
        if original_home.exists():
            project_paths = [
                original_home / "servers-install-v2" / "lsxtool",
                original_home / "servers-install-v2",
                original_home / "servers-install" / "lsxtool",
                original_home / "servers-install",
            ]
            for project_path in reversed(project_paths):
                if project_path.exists() and str(project_path) not in sys.path:
                    sys.path.insert(0, str(project_path))
            venv_paths = [
                original_home / "servers-install-v2" / "venv" / "lib" / "python3.11" / "site-packages",
                original_home / "servers-install-v2" / "venv" / "lib" / "python3.12" / "site-packages",
                original_home / "servers-install-v2" / "lsxtool" / "venv" / "lib" / "python3.11" / "site-packages",
                original_home / "servers-install-v2" / "lsxtool" / "venv" / "lib" / "python3.12" / "site-packages",
                original_home / "servers-install" / "lsxtool" / "venv" / "lib" / "python3.11" / "site-packages",
                original_home / "servers-install" / "lsxtool" / "venv" / "lib" / "python3.12" / "site-packages",
                original_home / "servers-install" / "venv" / "lib" / "python3.11" / "site-packages",
                original_home / "servers-install" / "venv" / "lib" / "python3.12" / "site-packages",
            ]
            for venv_site_packages in venv_paths:
                if venv_site_packages.exists() and str(venv_site_packages) not in sys.path:
                    sys.path.insert(0, str(venv_site_packages))
                    break
            pythonpath = os.environ.get('PYTHONPATH', '')
            for project_path in project_paths:
                if project_path.exists():
                    if pythonpath:
                        if str(project_path) not in pythonpath:
                            os.environ['PYTHONPATH'] = f"{project_path}:{pythonpath}"
                    else:
                        os.environ['PYTHONPATH'] = str(project_path)
                    break

# Asegurar que el proyecto raíz (CONTROL-PLANE) está en path para importar atlas
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Delegación al Control Plane ATLAS: un solo app, sin duplicar comandos
from atlas.cli.app import app

if __name__ == "__main__":
    app()
