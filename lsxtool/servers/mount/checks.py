"""
Módulo de verificaciones para montajes
Verifica entorno, dependencias y permisos
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm


def check_wsl(console: Console) -> bool:
    """
    Verifica si se está ejecutando en WSL
    
    Returns:
        True si está en WSL, False en caso contrario
    """
    # Verificar archivo /proc/version que contiene información sobre WSL
    try:
        with open("/proc/version", "r") as f:
            version_info = f.read().lower()
            is_wsl = "microsoft" in version_info or "wsl" in version_info
        
        if is_wsl:
            console.print("[green]✔[/green] Entorno WSL detectado")
        else:
            console.print("[yellow]⚠[/yellow] No se detectó entorno WSL (puede funcionar igualmente)")
        
        return is_wsl
    except Exception:
        console.print("[yellow]⚠[/yellow] No se pudo verificar entorno WSL")
        return False


def check_dependencies(console: Console) -> Dict[str, bool]:
    """
    Verifica la existencia de dependencias necesarias
    
    Returns:
        Dict con nombre de dependencia como clave y bool indicando si está instalada
    """
    dependencies = {
        "sshfs": "sshfs",
        "fusermount": "fusermount",
        "sshpass": "sshpass"
    }
    
    results = {}
    
    console.print("\n[cyan]Verificando dependencias...[/cyan]")
    
    for name, command in dependencies.items():
        try:
            result = subprocess.run(
                ["which", command],
                capture_output=True,
                text=True,
                check=False
            )
            
            installed = result.returncode == 0
            
            if installed:
                # Obtener versión si es posible
                version_result = subprocess.run(
                    [command, "--version"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=2
                )
                version_info = ""
                if version_result.returncode == 0:
                    version_line = version_result.stdout.split("\n")[0]
                    version_info = f" - {version_line[:50]}"
                
                console.print(f"  [green]✔[/green] {name}{version_info}")
            else:
                console.print(f"  [red]✘[/red] {name} - No instalado")
            
            results[name] = installed
        except Exception as e:
            console.print(f"  [red]✘[/red] {name} - Error al verificar: {e}")
            results[name] = False
    
    return results


def install_dependencies(missing: List[str], console: Console) -> bool:
    """
    Instala las dependencias faltantes usando apt
    
    Args:
        missing: Lista de nombres de paquetes a instalar
        console: Console de Rich para salida
    
    Returns:
        True si la instalación fue exitosa, False en caso contrario
    """
    if not missing:
        return True
    
    # Verificar permisos sudo
    if os.geteuid() != 0:
        console.print("[red]✘[/red] Se requieren permisos de root para instalar dependencias")
        console.print("[yellow]Ejecuta con sudo: sudo lsxtool servers mount sshfs[/yellow]")
        return False
    
    # Mapear nombres a paquetes apt
    package_map = {
        "sshfs": "sshfs",
        "fusermount": "fuse",
        "sshpass": "sshpass"
    }
    
    packages_to_install = [package_map.get(name, name) for name in missing]
    packages_to_install = list(set(packages_to_install))  # Eliminar duplicados
    
    console.print(f"\n[yellow]Instalando paquetes: {', '.join(packages_to_install)}[/yellow]")
    
    try:
        # Actualizar lista de paquetes
        console.print("[dim]Actualizando lista de paquetes...[/dim]")
        update_result = subprocess.run(
            ["apt-get", "update", "-qq"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if update_result.returncode != 0:
            console.print("[red]✘[/red] Error al actualizar lista de paquetes")
            return False
        
        # Instalar paquetes
        install_result = subprocess.run(
            ["apt-get", "install", "-y", "-qq"] + packages_to_install,
            capture_output=True,
            text=True,
            check=False
        )
        
        if install_result.returncode == 0:
            console.print(f"[green]✔[/green] Paquetes instalados correctamente")
            return True
        else:
            console.print(f"[red]✘[/red] Error al instalar paquetes")
            if install_result.stderr:
                console.print(f"[dim]{install_result.stderr}[/dim]")
            return False
    except Exception as e:
        console.print(f"[red]✘[/red] Error durante la instalación: {e}")
        return False


def verify_dependencies_with_install(console: Console) -> bool:
    """
    Verifica dependencias y ofrece instalarlas si faltan
    
    Returns:
        True si todas las dependencias están disponibles, False en caso contrario
    """
    results = check_dependencies(console)
    
    missing = [name for name, installed in results.items() if not installed]
    
    if not missing:
        return True
    
    console.print(f"\n[yellow]⚠ Faltan {len(missing)} dependencia(s): {', '.join(missing)}[/yellow]")
    
    # Verificar si tenemos permisos sudo
    has_sudo = os.geteuid() == 0
    
    if not has_sudo:
        console.print("[yellow]Se requieren permisos de root para instalar dependencias[/yellow]")
        if Confirm.ask("\n¿Deseas continuar sin instalar? (puedes instalarlas manualmente después)", default=False):
            return False
        else:
            console.print("[yellow]Ejecuta con sudo: sudo lsxtool servers mount sshfs[/yellow]")
            return False
    
    if Confirm.ask(f"\n¿Deseas instalar las dependencias faltantes?", default=True):
        return install_dependencies(missing, console)
    else:
        console.print("[yellow]Instalación cancelada. Instala manualmente las dependencias antes de continuar.[/yellow]")
        return False


def check_mount_point(mount_point: Path, console: Console) -> Tuple[bool, Optional[str]]:
    """
    Verifica el estado de un punto de montaje
    
    Args:
        mount_point: Ruta del punto de montaje
        console: Console de Rich para salida
    
    Returns:
        Tuple (is_mounted, mount_info)
        - is_mounted: True si está montado
        - mount_info: Información del montaje o None
    """
    try:
        # Verificar si el directorio existe
        if not mount_point.exists():
            return False, None
        
        # Verificar si está montado usando findmnt
        result = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE,TARGET,FSTYPE", str(mount_point)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0 and result.stdout.strip():
            mount_info = result.stdout.strip()
            return True, mount_info
        
        # Alternativa: verificar usando /proc/mounts
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        target = parts[1]
                        if target == str(mount_point) or target == str(mount_point.resolve()):
                            return True, line.strip()
        except Exception:
            pass
        
        return False, None
    except Exception as e:
        console.print(f"[yellow]⚠ Error al verificar punto de montaje: {e}[/yellow]")
        return False, None


def verify_mount_access(mount_point: Path, console: Console) -> bool:
    """
    Verifica que el punto de montaje sea accesible
    
    Args:
        mount_point: Ruta del punto de montaje
        console: Console de Rich para salida
    
    Returns:
        True si es accesible, False en caso contrario
    """
    try:
        # Verificar que el directorio existe
        if not mount_point.exists():
            console.print(f"[red]✘[/red] El directorio {mount_point} no existe")
            return False
        
        # Verificar que es un directorio
        if not mount_point.is_dir():
            console.print(f"[red]✘[/red] {mount_point} no es un directorio")
            return False
        
        # Intentar listar contenido (test de acceso)
        try:
            list(mount_point.iterdir())
            console.print(f"[green]✔[/green] Punto de montaje accesible")
            return True
        except PermissionError:
            console.print(f"[red]✘[/red] Sin permisos para acceder a {mount_point}")
            return False
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Error al acceder: {e}")
            return False
    except Exception as e:
        console.print(f"[red]✘[/red] Error al verificar acceso: {e}")
        return False
