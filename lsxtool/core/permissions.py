"""
Módulo Permissions - Verificación y gestión de permisos
"""

import os
from pathlib import Path
from typing import Optional
from rich.console import Console


def check_write_permission(path: Path) -> bool:
    """
    Verifica si se tiene permiso de escritura en una ruta
    
    Args:
        path: Ruta a verificar
    
    Returns:
        True si se puede escribir
    """
    try:
        if path.is_file():
            # Verificar si el archivo es escribible
            return os.access(path, os.W_OK)
        elif path.is_dir():
            # Verificar si el directorio es escribible
            return os.access(path, os.W_OK)
        else:
            # Verificar si el directorio padre es escribible
            return os.access(path.parent, os.W_OK)
    except Exception:
        return False


def check_read_permission(path: Path) -> bool:
    """
    Verifica si se tiene permiso de lectura en una ruta
    
    Args:
        path: Ruta a verificar
    
    Returns:
        True si se puede leer
    """
    try:
        if path.exists():
            return os.access(path, os.R_OK)
        else:
            return os.access(path.parent, os.R_OK)
    except Exception:
        return False


def check_execute_permission(path: Path) -> bool:
    """
    Verifica si se tiene permiso de ejecución en una ruta
    
    Args:
        path: Ruta a verificar
    
    Returns:
        True si se puede ejecutar
    """
    try:
        if path.exists():
            return os.access(path, os.X_OK)
        return False
    except Exception:
        return False


def require_root(console: Optional[Console] = None) -> bool:
    """
    Verifica si se tienen permisos de root
    
    Args:
        console: Console de Rich para mostrar error
    
    Returns:
        True si se tiene root
    """
    if os.geteuid() == 0:
        return True
    
    if console:
        console.print("[red]✘ Se requieren permisos de root[/red]")
        console.print("[yellow]Ejecuta con sudo[/yellow]")
    
    return False


def require_sudo(console: Optional[Console] = None) -> bool:
    """
    Verifica si el usuario puede usar sudo
    
    Args:
        console: Console de Rich para mostrar error
    
    Returns:
        True si se puede usar sudo
    """
    import subprocess
    
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1
        )
        
        if result.returncode == 0:
            return True
        
        if console:
            console.print("[yellow]⚠ Se requiere sudo (puede pedir contraseña)[/yellow]")
        
        return False
    except Exception:
        if console:
            console.print("[yellow]⚠ No se pudo verificar sudo[/yellow]")
        return False
