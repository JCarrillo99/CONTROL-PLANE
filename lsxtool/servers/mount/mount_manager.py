"""
Gestión de montajes registrados por lsxtool
Almacena información sobre montajes gestionados
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

MOUNTS_FILE = Path.home() / ".lsxtool" / "mounts.json"


@dataclass
class MountInfo:
    """Información de un montaje gestionado"""
    name: str
    mount_type: str  # sshfs, bind, nfs, etc.
    source: str  # Origen del montaje
    destination: Path  # Punto de montaje
    options: Optional[Dict[str, str]] = None
    created_at: Optional[str] = None
    last_checked: Optional[str] = None


def ensure_mounts_dir() -> None:
    """Asegura que el directorio de montajes existe"""
    MOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_mounts() -> Dict[str, MountInfo]:
    """
    Carga montajes desde archivo
    
    Returns:
        Dict con destino como clave y MountInfo como valor
    """
    ensure_mounts_dir()
    
    if not MOUNTS_FILE.exists():
        return {}
    
    try:
        with open(MOUNTS_FILE, "r") as f:
            data = json.load(f)
        
        mounts = {}
        for dest, mount_data in data.items():
            mount_data["destination"] = Path(mount_data["destination"])
            mounts[dest] = MountInfo(**mount_data)
        
        return mounts
    except Exception:
        return {}


def save_mounts(mounts: Dict[str, MountInfo]) -> None:
    """Guarda montajes en archivo"""
    ensure_mounts_dir()
    
    data = {}
    for dest, mount_info in mounts.items():
        mount_dict = asdict(mount_info)
        mount_dict["destination"] = str(mount_dict["destination"])
        data[dest] = mount_dict
    
    with open(MOUNTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_mount(mount_info: MountInfo) -> bool:
    """
    Registra un nuevo montaje
    
    Args:
        mount_info: Información del montaje
    
    Returns:
        True si se agregó correctamente
    """
    mounts = load_mounts()
    dest_str = str(mount_info.destination)
    
    if not mount_info.created_at:
        mount_info.created_at = datetime.now().isoformat()
    
    mounts[dest_str] = mount_info
    save_mounts(mounts)
    return True


def remove_mount(destination: Path) -> bool:
    """
    Elimina un montaje del registro
    
    Args:
        destination: Punto de montaje a eliminar
    
    Returns:
        True si se eliminó, False si no existe
    """
    mounts = load_mounts()
    dest_str = str(destination)
    
    if dest_str not in mounts:
        return False
    
    del mounts[dest_str]
    save_mounts(mounts)
    return True


def get_mount(destination: Path) -> Optional[MountInfo]:
    """Obtiene información de un montaje"""
    mounts = load_mounts()
    dest_str = str(destination)
    return mounts.get(dest_str)


def list_mounts() -> List[MountInfo]:
    """Lista todos los montajes registrados"""
    mounts = load_mounts()
    return list(mounts.values())


def update_mount_check(destination: Path) -> None:
    """Actualiza la fecha de última verificación de un montaje"""
    mounts = load_mounts()
    dest_str = str(destination)
    
    if dest_str in mounts:
        mounts[dest_str].last_checked = datetime.now().isoformat()
        save_mounts(mounts)
