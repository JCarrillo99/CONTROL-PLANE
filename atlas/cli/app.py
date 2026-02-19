"""
Aplicación CLI unificada (ATLAS / LSX Tool).

Solo compone submódulos y comandos; la lógica vive en core y providers.
Por compatibilidad, los submódulos se delegan a lsxtool mientras se migra.
"""

import sys
import os
from pathlib import Path

# Proyecto raíz (CONTROL-PLANE) para .env y sys.path
_ROOT = Path(__file__).resolve().parents[2]
if _ROOT not in (Path(p).resolve() for p in sys.path):
    sys.path.insert(0, str(_ROOT))

# Cargar .env del proyecto
try:
    from dotenv import load_dotenv
    _env = _ROOT / ".env"
    if _env.exists():
        load_dotenv(_env)
except Exception:
    pass

# Ajuste sys.path cuando se ejecuta con sudo (igual que lsxtool/cli.py)
if os.geteuid() == 0:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        home = Path(f"/home/{sudo_user}")
        if home.exists():
            for p in reversed([home / "servers-install-v2" / "lsxtool", home / "servers-install-v2",
                               home / "servers-install" / "lsxtool", home / "servers-install"]):
                if p.exists() and str(p) not in sys.path:
                    sys.path.insert(0, str(p))

import typer
from rich.console import Console
from rich.panel import Panel

# Delegación a lsxtool: CLI como wrappers; la lógica se migrará a atlas/core + providers
from lsxtool.networks.cli import app as networks_app
from lsxtool.servers.cli import app as servers_app
from lsxtool.devops.cli import app as devops_app
from lsxtool.infra.cli import app as infra_app
from lsxtool.providers.cli import app as providers_app

app = typer.Typer(
    name="lsxtool",
    help="LSX Tool - CLI Corporativa para gestión de TI (ATLAS Control Plane)",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()

app.add_typer(networks_app, name="networks", help="Gestión de Redes y DNS")
app.add_typer(servers_app, name="servers", help="Gestión de Servidores (Nginx, Apache, Traefik)")
app.add_typer(devops_app, name="devops", help="Herramientas DevOps (CI/CD, Jenkins, GitLab)")
app.add_typer(infra_app, name="infra", help="Gestión de Infraestructura")
app.add_typer(providers_app, name="providers", help="Configuración de providers y capacidades")


@app.command()
def version():
    """Muestra la versión de LSX Tool"""
    console.print(Panel.fit(
        "[bold cyan]LSX Tool (ATLAS)[/bold cyan]\n"
        "[dim]CLI Corporativa para gestión de TI - Control Plane[/dim]\n\n"
        "[bold]Versión:[/bold] 1.0.0\n"
        "[bold]Estado:[/bold] /var/lib/lsx/atlas\n"
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
    table.add_row("networks", "Gestión de Redes y DNS", "dns, status, test")
    table.add_row("servers", "Gestión de Servidores Web", "nginx, apache, traefik, status")
    table.add_row("devops", "Herramientas DevOps", "ci, jenkins, gitlab")
    table.add_row("infra", "Infraestructura", "monitoring, backup, health")
    console.print(table)
    console.print("\n[dim]Usa 'lsxtool <departamento> --help' para ver comandos específicos[/dim]")


def main():
    app()
