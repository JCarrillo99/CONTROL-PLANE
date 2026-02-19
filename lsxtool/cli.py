#!/usr/bin/env python3
"""
LSX Tool - CLI Corporativa Unificada
Herramienta interna para gestión de TI (Redes, Servidores, DevOps, Infraestructura)
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
# NO re-ejecutar automáticamente para evitar bucles infinitos
if os.geteuid() == 0:  # Ejecutando como root
    # Intentar encontrar el venv del usuario original y agregar al sys.path
    original_user = os.environ.get('SUDO_USER')
    if original_user:
        original_home = Path(f"/home/{original_user}")
        if original_home.exists():
            # Buscar el proyecto y agregar al sys.path (servers-install-v2 y servers-install)
            project_paths = [
                original_home / "servers-install-v2" / "lsxtool",
                original_home / "servers-install-v2",
                original_home / "servers-install" / "lsxtool",
                original_home / "servers-install",
            ]
            # Insertar en orden inverso para que lsxtool quede primero (ahí están providers, networks, servers, etc.)
            for project_path in reversed(project_paths):
                if project_path.exists() and str(project_path) not in sys.path:
                    sys.path.insert(0, str(project_path))
            
            # Buscar venv y agregar site-packages al sys.path
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
            
            # También ajustar PYTHONPATH para subprocesos
            pythonpath = os.environ.get('PYTHONPATH', '')
            for project_path in project_paths:
                if project_path.exists():
                    if pythonpath:
                        if str(project_path) not in pythonpath:
                            os.environ['PYTHONPATH'] = f"{project_path}:{pythonpath}"
                    else:
                        os.environ['PYTHONPATH'] = str(project_path)
                    break

import typer
from rich.console import Console
from rich.panel import Panel

# Importar submódulos de departamentos
from networks.cli import app as networks_app
from servers.cli import app as servers_app
from devops.cli import app as devops_app
from infra.cli import app as infra_app
from providers.cli import app as providers_app

# CLI principal
app = typer.Typer(
    name="lsxtool",
    help="LSX Tool - CLI Corporativa para gestión de TI",
    add_completion=False,
    no_args_is_help=True
)

console = Console()

# Registrar submódulos como subcomandos
app.add_typer(networks_app, name="networks", help="Gestión de Redes y DNS")
app.add_typer(servers_app, name="servers", help="Gestión de Servidores (Nginx, Apache, Traefik)")
app.add_typer(devops_app, name="devops", help="Herramientas DevOps (CI/CD, Jenkins, GitLab)")
app.add_typer(infra_app, name="infra", help="Gestión de Infraestructura")
app.add_typer(providers_app, name="providers", help="Configuración de providers y capacidades")


@app.command()
def version():
    """Muestra la versión de LSX Tool"""
    console.print(Panel.fit(
        "[bold cyan]LSX Tool[/bold cyan]\n"
        "[dim]CLI Corporativa para gestión de TI[/dim]\n\n"
        "[bold]Versión:[/bold] 1.0.0\n"
        "[bold]Entorno:[/bold] Windows 10 + WSL (Debian)\n"
        "[bold]Departamentos:[/bold] Networks, Servers, DevOps, Infra",
        border_style="cyan"
    ))


@app.command()
def info():
    """Muestra información sobre LSX Tool"""
    console.print(Panel.fit("[bold cyan]LSX Tool - Información[/bold cyan]", border_style="cyan"))
    
    from rich.table import Table
    
    table = Table(title="Departamentos Disponibles", show_header=True, header_style="bold cyan")
    table.add_column("Departamento", style="cyan", width=15)
    table.add_column("Descripción", style="green")
    table.add_column("Comandos", style="yellow")
    
    table.add_row(
        "networks",
        "Gestión de Redes y DNS",
        "dns, status, test"
    )
    table.add_row(
        "servers",
        "Gestión de Servidores Web",
        "nginx, apache, traefik, status"
    )
    table.add_row(
        "devops",
        "Herramientas DevOps",
        "ci, jenkins, gitlab"
    )
    table.add_row(
        "infra",
        "Infraestructura",
        "monitoring, backup, health"
    )
    
    console.print(table)
    console.print("\n[dim]Usa 'lsxtool <departamento> --help' para ver comandos específicos[/dim]")


if __name__ == "__main__":
    app()
