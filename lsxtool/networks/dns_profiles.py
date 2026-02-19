"""
Gestión de perfiles DNS
Almacena y gestiona perfiles DNS configurables
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from .dns_manager import DNSConfig, DNS_NORMAL, DNS_CORPORATIVO

PROFILES_FILE = Path.home() / ".lsxtool" / "dns_profiles.json"


@dataclass
class DNSProfile:
    """Perfil DNS con nombre y configuración"""
    name: str
    description: str
    servers: List[str]
    search_domains: Optional[List[str]] = None


def ensure_profiles_dir() -> None:
    """Asegura que el directorio de perfiles existe"""
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_profiles() -> Dict[str, DNSProfile]:
    """
    Carga perfiles DNS desde archivo
    
    Returns:
        Dict con nombre de perfil como clave y DNSProfile como valor
    """
    ensure_profiles_dir()
    
    # Perfiles predefinidos
    default_profiles = {
        "normal": DNSProfile(
            name="Normal/Público",
            description="Google DNS y Cloudflare DNS",
            servers=DNS_NORMAL.servers
        ),
        "corp": DNSProfile(
            name="Corporativo",
            description="DNS internos de la red corporativa",
            servers=DNS_CORPORATIVO.servers
        )
    }
    
    if not PROFILES_FILE.exists():
        # Crear archivo con perfiles por defecto
        save_profiles(default_profiles)
        return default_profiles
    
    try:
        with open(PROFILES_FILE, "r") as f:
            data = json.load(f)
        
        profiles = {}
        for name, profile_data in data.items():
            profiles[name] = DNSProfile(**profile_data)
        
        # Asegurar que los perfiles por defecto existen
        for name, profile in default_profiles.items():
            if name not in profiles:
                profiles[name] = profile
        
        return profiles
    except Exception:
        # Si hay error, retornar solo los por defecto
        return default_profiles


def save_profiles(profiles: Dict[str, DNSProfile]) -> None:
    """Guarda perfiles DNS en archivo"""
    ensure_profiles_dir()
    
    data = {}
    for name, profile in profiles.items():
        data[name] = asdict(profile)
    
    with open(PROFILES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_profile(name: str) -> Optional[DNSProfile]:
    """Obtiene un perfil por nombre"""
    profiles = load_profiles()
    return profiles.get(name)


def add_profile(profile: DNSProfile) -> bool:
    """
    Agrega un nuevo perfil DNS
    
    Args:
        profile: Perfil DNS a agregar
    
    Returns:
        True si se agregó correctamente, False si ya existe
    """
    profiles = load_profiles()
    
    # Normalizar nombre (usar minúsculas como clave)
    key = profile.name.lower().replace(" ", "-").replace("/", "-")
    
    if key in profiles:
        return False
    
    profiles[key] = profile
    save_profiles(profiles)
    return True


def remove_profile(name: str) -> bool:
    """
    Elimina un perfil DNS
    
    Args:
        name: Nombre del perfil a eliminar
    
    Returns:
        True si se eliminó, False si no existe o es un perfil por defecto
    """
    profiles = load_profiles()
    
    # Normalizar nombre
    key = name.lower().replace(" ", "-").replace("/", "-")
    
    # No permitir eliminar perfiles por defecto
    if key in ["normal", "corp"]:
        return False
    
    if key not in profiles:
        return False
    
    del profiles[key]
    save_profiles(profiles)
    return True


def list_profiles() -> List[DNSProfile]:
    """Lista todos los perfiles DNS"""
    profiles = load_profiles()
    return list(profiles.values())


def profile_to_dns_config(profile: DNSProfile) -> DNSConfig:
    """Convierte un DNSProfile a DNSConfig"""
    return DNSConfig(
        name=profile.name,
        description=profile.description,
        servers=profile.servers,
        search_domains=profile.search_domains
    )
