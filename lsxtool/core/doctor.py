"""
Módulo Doctor - Verificación de herramientas y requisitos del sistema
"""

import subprocess
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


def check_tool(tool_name: str) -> Tuple[bool, Optional[str]]:
    """
    Verifica si una herramienta está instalada y disponible
    
    Args:
        tool_name: Nombre del comando a verificar
    
    Returns:
        Tuple (is_available, version_info)
    """
    try:
        result = subprocess.run(
            ["which", tool_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=2
        )
        
        if result.returncode != 0:
            return False, None
        
        # Intentar obtener versión
        version_info = None
        try:
            version_result = subprocess.run(
                [tool_name, "--version"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            if version_result.returncode == 0:
                version_line = version_result.stdout.split("\n")[0]
                version_info = version_line[:50]
        except Exception:
            pass
        
        return True, version_info
    except Exception:
        return False, None


def check_permissions() -> Dict[str, bool]:
    """
    Verifica permisos del usuario actual
    
    Returns:
        Dict con tipo de permiso como clave y bool como valor
    """
    return {
        "root": os.geteuid() == 0,
        "sudo": _check_sudo(),
        "ssh_keys": _check_ssh_keys(),
        "git_config": _check_git_config()
    }


def _check_sudo() -> bool:
    """Verifica si el usuario puede usar sudo"""
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_ssh_keys() -> bool:
    """Verifica si existen claves SSH"""
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return False
    
    # Verificar si hay claves privadas
    key_files = list(ssh_dir.glob("id_*"))
    return len([f for f in key_files if not f.name.endswith(".pub")]) > 0


def _check_git_config() -> bool:
    """Verifica si git está configurado"""
    try:
        result = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1
        )
        return result.returncode == 0 and result.stdout.strip()
    except Exception:
        return False


def check_connectivity(host: str, port: int = 22, timeout: int = 3) -> bool:
    """
    Verifica conectividad básica a un host
    
    Args:
        host: Hostname o IP
        port: Puerto a verificar
        timeout: Timeout en segundos
    
    Returns:
        True si hay conectividad
    """
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def run_doctor(console: Console, required_tools: Optional[List[str]] = None) -> Dict[str, bool]:
    """
    Ejecuta verificación completa del sistema (doctor)
    
    Args:
        console: Console de Rich para salida
        required_tools: Lista de herramientas requeridas
    
    Returns:
        Dict con resultados de verificación
    """
    if required_tools is None:
        required_tools = ["git", "ssh", "curl", "wget"]
    
    console.print(Panel.fit("[bold cyan]Doctor - Verificación del Sistema[/bold cyan]", border_style="cyan"))
    
    results = {}
    
    # Verificar herramientas
    console.print("\n[bold]Herramientas[/bold]")
    tool_table = Table(show_header=True, header_style="bold cyan")
    tool_table.add_column("Herramienta", style="cyan")
    tool_table.add_column("Estado", style="green")
    tool_table.add_column("Versión", style="dim")
    
    for tool in required_tools:
        available, version = check_tool(tool)
        status = "[green]✔ Disponible[/green]" if available else "[red]✘ No encontrado[/red]"
        version_str = version or "[dim]N/A[/dim]"
        tool_table.add_row(tool, status, version_str)
        results[f"tool_{tool}"] = available
    
    console.print(tool_table)
    
    # Verificar permisos
    console.print("\n[bold]Permisos[/bold]")
    perm_table = Table(show_header=True, header_style="bold cyan")
    perm_table.add_column("Permiso", style="cyan")
    perm_table.add_column("Estado", style="green")
    
    permissions = check_permissions()
    for perm_name, has_perm in permissions.items():
        status = "[green]✔ Disponible[/green]" if has_perm else "[yellow]⚠ No disponible[/yellow]"
        perm_table.add_row(perm_name.replace("_", " ").title(), status)
        results[f"perm_{perm_name}"] = has_perm
    
    console.print(perm_table)
    
    # Resumen
    all_tools_ok = all(results.get(f"tool_{tool}", False) for tool in required_tools)
    
    if all_tools_ok:
        console.print("\n[bold green]✅ Todas las herramientas requeridas están disponibles[/bold green]")
    else:
        console.print("\n[yellow]⚠️ Algunas herramientas faltan[/yellow]")
        missing = [tool for tool in required_tools if not results.get(f"tool_{tool}", False)]
        console.print(f"[dim]Faltan: {', '.join(missing)}[/dim]")
    
    return results
