"""
Detección de versiones de servidores web
"""

import subprocess
from typing import Optional
from rich.console import Console


def get_apache_version() -> Optional[str]:
    """
    Obtiene la versión de Apache instalada
    
    Returns:
        Versión de Apache (ej: "2.4.65") o None si no está instalado
    """
    try:
        result = subprocess.run(
            ["apachectl", "-v"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Buscar línea con "Server version: Apache/X.X.X"
            for line in result.stdout.split("\n"):
                if "Server version:" in line:
                    # Extraer versión: Apache/2.4.65
                    parts = line.split("Apache/")
                    if len(parts) > 1:
                        version = parts[1].split()[0]
                        return version
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return None


def get_nginx_version() -> Optional[str]:
    """
    Obtiene la versión de Nginx instalada
    
    Returns:
        Versión de Nginx (ej: "1.18.0") o None si no está instalado
    """
    try:
        # Nginx escribe la versión en stderr, no en stdout
        result = subprocess.run(
            ["nginx", "-v"],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            timeout=5
        )
        
        # Nginx escribe la versión en stderr
        output = result.stderr if result.stderr else result.stdout
        
        # Buscar versión: nginx version: nginx/1.18.0
        if output and "nginx version:" in output:
            parts = output.split("nginx/")
            if len(parts) > 1:
                version = parts[1].strip()
                return version
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return None


def get_server_version_display(backend_type: Optional[str]) -> str:
    """
    Obtiene la versión del servidor web para mostrar
    
    Args:
        backend_type: Tipo de backend (apache, nginx, traefik)
    
    Returns:
        String formateado: "Apache 2.4.65" o "Nginx 1.18.0" o "Traefik (internal)"
    """
    if not backend_type:
        return "UNKNOWN N/A"
    
    backend_lower = backend_type.lower()
    
    if backend_lower == "apache":
        version = get_apache_version()
        if version:
            return f"Apache {version}"
        return "Apache N/A"
    elif backend_lower == "nginx":
        version = get_nginx_version()
        if version:
            return f"Nginx {version}"
        return "Nginx N/A"
    elif backend_lower == "traefik":
        # Servicio interno de Traefik (dashboard)
        return "[dim]Traefik (internal)[/dim]"
    else:
        return f"{backend_type.upper()} N/A"
