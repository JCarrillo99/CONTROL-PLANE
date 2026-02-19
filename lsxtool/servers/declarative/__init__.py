"""
Sistema Declarativo de Infraestructura
Orquestador central estilo Terraform/Kubernetes para lsxtool
"""

import os
from pathlib import Path
from typing import Optional


def chown_to_project_owner(path: Path, base_dir: Path, recursive: bool = False) -> None:
    """
    Si el proceso corre como root, asigna al path el dueño del directorio del proyecto
    para que el usuario que ejecutó (vía sudo) pueda editar los archivos en .lsxtool/
    """
    if os.geteuid() != 0:
        return
    try:
        st = base_dir.stat()
        uid, gid = st.st_uid, st.st_gid
        os.chown(path, uid, gid)
        if recursive and path.is_dir():
            for p in path.rglob("*"):
                try:
                    os.chown(p, uid, gid)
                except OSError:
                    pass
    except OSError:
        pass


def get_declarative_root(base_dir: Path) -> Path:
    """
    Obtiene el directorio raíz del sistema declarativo (.lsxtool/)
    
    Args:
        base_dir: Directorio base del proyecto (servers-install-v2/)
    
    Returns:
        Path a .lsxtool/
    """
    declarative_root = base_dir / ".lsxtool"
    declarative_root.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(declarative_root, base_dir, recursive=True)
    return declarative_root


__all__ = ["get_declarative_root", "chown_to_project_owner"]
