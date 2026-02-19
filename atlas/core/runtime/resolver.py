"""
Resolución de rutas de estado y proyecto.

- state_root(): directorio canónico de estado/runtime (/var/lib/lsx/atlas/).
- project_base(): directorio base del proyecto (para compatibilidad con .lsxtool en repo).

El core NO escribe en disco; solo expone estas rutas. Quién escribe (CLI/providers)
debe usar state_root() para estado persistente y, si se desea compatibilidad legacy,
project_base() para .lsxtool en el proyecto.
"""

import os
from pathlib import Path
from typing import Optional


# Ruta canónica del estado del Control Plane (fuera del repo)
ATLAS_STATE_ROOT = Path("/var/lib/lsx/atlas")


def state_root() -> Path:
    """
    Directorio raíz del estado y runtime de ATLAS.
    Nunca dentro del repo; siempre /var/lib/lsx/atlas/.
    """
    return ATLAS_STATE_ROOT


def project_base() -> Optional[Path]:
    """
    Directorio base del proyecto (donde podría existir .lsxtool).
    Usado para compatibilidad con flujos que aún leen/escriben en proyecto/.lsxtool.
    Resolución: LSXTOOL_DEV → repo que contiene .lsxtool; si no, None (solo estado en state_root).
    """
    # Variable de entorno explícita
    explicit = os.environ.get("LSXTOOL_PROJECT_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    # Modo desarrollo: buscar repo que contenga .lsxtool (desde cwd o desde __file__)
    candidates = list(Path.cwd().parents) + [Path.cwd()]
    for d in candidates:
        if (d / ".lsxtool").exists():
            return d.resolve()

    try:
        # Desde este paquete: atlas/core/runtime/resolver.py → subir hasta repo
        p = Path(__file__).resolve().parent
        for _ in range(8):
            if (p / ".lsxtool").exists():
                return p
            if (p / "atlas").exists() and (p / "lsxtool").exists():
                return p
            parent = p.parent
            if parent == p:
                break
            p = parent
    except Exception:
        pass
    return None
