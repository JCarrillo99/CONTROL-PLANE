"""
Catálogos controlados para metadatos de sitios
Todos los valores deben provenir de estos catálogos para mantener consistencia
"""

from typing import List, Dict, Optional
from pathlib import Path
import json

CATALOGS_DIR = Path.home() / ".lsxtool" / "sites" / "catalogs"


# Catálogos por defecto (se pueden personalizar)
DEFAULT_OWNERS = [
    "equipo-desarrollo",
    "equipo-infraestructura",
    "equipo-seguridad",
    "equipo-operaciones",
    "equipo-citas",
    "equipo-registroentidad",
    "equipo-ady",
    "equipo-stic",
    "equipo-lsx",
]

DEFAULT_PROVIDERS = [
    "STIC",
    "LSX",
    "EXTERNAL",
]

DEFAULT_SERVICE_TYPES = [
    "web",
    "api",
    "admin",
    "static",
]

DEFAULT_ENVIRONMENTS = [
    "dev",
    "qa",
    "prod",
]

DEFAULT_BACKENDS = [
    "apache",
    "nginx",
]

# Catálogo de backends con sus puertos estándar
BACKEND_PORTS = {
    "nginx": 9100,
    "apache": 9200,
}

# Catálogos para tecnologías runtime
DEFAULT_TECH_PROVIDERS = {
    "node": ["volta", "nvm", "system", "asdf", "container"],
    "php": ["system", "phpbrew", "container"],
    "python": ["system", "pyenv", "asdf", "container"],
}

DEFAULT_TECH_MANAGERS = {
    "node": ["npm", "yarn", "pnpm", "bun"],
    "php": ["composer"],
    "python": ["pip", "poetry"],
}


def get_backend_port(backend: str) -> Optional[int]:
    """
    Obtiene el puerto estándar de un backend
    
    Args:
        backend: Tipo de backend (nginx, apache)
    
    Returns:
        Puerto estándar o None si no existe
    """
    return BACKEND_PORTS.get(backend.lower())


def ensure_catalogs_dir() -> None:
    """Asegura que el directorio de catálogos existe"""
    CATALOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_catalog_file(catalog_name: str) -> Path:
    """Obtiene la ruta del archivo de catálogo"""
    ensure_catalogs_dir()
    return CATALOGS_DIR / f"{catalog_name}.json"


def load_catalog(catalog_name: str, default: List[str]) -> List[str]:
    """
    Carga un catálogo desde archivo o retorna el default
    
    Args:
        catalog_name: Nombre del catálogo
        default: Lista por defecto si no existe el archivo
    
    Returns:
        Lista de valores del catálogo
    """
    catalog_file = get_catalog_file(catalog_name)
    
    if catalog_file.exists():
        try:
            with open(catalog_file, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    
    # Si no existe o hay error, crear con valores por defecto
    save_catalog(catalog_name, default)
    return default


def save_catalog(catalog_name: str, values: List[str]) -> bool:
    """
    Guarda un catálogo
    
    Args:
        catalog_name: Nombre del catálogo
        values: Lista de valores
    
    Returns:
        True si se guardó correctamente
    """
    ensure_catalogs_dir()
    catalog_file = get_catalog_file(catalog_name)
    
    try:
        with open(catalog_file, "w") as f:
            json.dump(values, f, indent=2)
        return True
    except Exception:
        return False


def get_owners() -> List[str]:
    """Obtiene catálogo de owners/equipos"""
    return load_catalog("owners", DEFAULT_OWNERS)


def get_providers() -> List[str]:
    """Obtiene catálogo de proveedores"""
    return load_catalog("providers", DEFAULT_PROVIDERS)


def get_service_types() -> List[str]:
    """Obtiene catálogo de tipos de servicio"""
    return load_catalog("service_types", DEFAULT_SERVICE_TYPES)


def get_environments() -> List[str]:
    """Obtiene catálogo de ambientes"""
    return load_catalog("environments", DEFAULT_ENVIRONMENTS)


def get_backends() -> List[str]:
    """Obtiene catálogo de backends"""
    return load_catalog("backends", DEFAULT_BACKENDS)


def get_backend_versions(backend: str) -> List[str]:
    """
    Obtiene versiones disponibles de un backend específico
    
    Args:
        backend: Tipo de backend (apache, nginx)
    
    Returns:
        Lista de versiones disponibles
    """
    from .server_version import get_apache_version, get_nginx_version
    
    backend_lower = backend.lower()
    
    if backend_lower == "apache":
        version = get_apache_version()
        if version:
            return [version]
        return []
    elif backend_lower == "nginx":
        version = get_nginx_version()
        if version:
            return [version]
        return []
    
    return []


def get_tech_providers(tech: str) -> List[str]:
    """
    Obtiene catálogo de tech_provider para una tecnología
    
    Args:
        tech: Tecnología (node, php, python)
    
    Returns:
        Lista de tech_providers válidos
    """
    tech_lower = tech.lower()
    default = DEFAULT_TECH_PROVIDERS.get(tech_lower, [])
    return load_catalog(f"tech_providers_{tech_lower}", default)


def get_tech_managers(tech: str) -> List[str]:
    """
    Obtiene catálogo de tech_manager para una tecnología
    
    Args:
        tech: Tecnología (node, php, python)
    
    Returns:
        Lista de tech_managers válidos
    """
    tech_lower = tech.lower()
    default = DEFAULT_TECH_MANAGERS.get(tech_lower, [])
    return load_catalog(f"tech_managers_{tech_lower}", default)
