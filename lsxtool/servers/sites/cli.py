"""
CLI para gestión de sitios - Comandos adicionales
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from servers.sites.sites_manager import get_site_info, load_all_sites
from servers.sites.manifest import ServiceManifest, save_manifest, load_manifest, delete_manifest
from servers.sites.traefik_parser import parse_traefik_config

app = typer.Typer(
    name="sites",
    help="Gestión de sitios web configurados",
    add_completion=False
)
console = Console()


def _show_site_info(domain: str, console: Console):
    """Muestra información detallada de un sitio (ficha técnica)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    
    from servers.sites.sites_manager import get_site_info
    
    BASE_DIR = Path(__file__).parent.parent.parent.parent.parent.resolve()
    
    site_info = get_site_info(domain, BASE_DIR, console)
    
    if not site_info:
        console.print(f"[red]❌ Sitio '{domain}' no encontrado[/red]")
        return
    
    console.print(Panel.fit(f"[bold cyan]Ficha Técnica - {domain}[/bold cyan]", border_style="cyan"))
    
    # Información principal
    main_table = Table(show_header=False, box=None, title="Información Principal")
    main_table.add_column("Campo", style="cyan", width=20)
    main_table.add_column("Valor", style="green")
    
    main_table.add_row("Dominio", site_info.domain)
    main_table.add_row("Proveedor", site_info.provider)
    main_table.add_row("Ambiente", site_info.environment.upper())
    main_table.add_row("Tipo de Servicio", site_info.service_type.upper())
    main_table.add_row("Dueño/Equipo", site_info.owner)
    
    if site_info.manifest and site_info.manifest.description:
        main_table.add_row("Descripción", site_info.manifest.description)
    
    console.print(main_table)
    
    # Información técnica
    console.print("\n[bold]Información Técnica[/bold]")
    tech_table = Table(show_header=False, box=None)
    tech_table.add_column("Campo", style="cyan", width=20)
    tech_table.add_column("Valor", style="green")
    
    tech_table.add_row("Backend Type", site_info.backend_type.upper())
    tech_table.add_row("Backend Version", site_info.backend_version)
    tech_table.add_row("Target", site_info.target)
    tech_table.add_row("Ruta en Servidor", site_info.path)
    
    if site_info.manifest and site_info.manifest.tags:
        tech_table.add_row("Tags", ", ".join(site_info.manifest.tags))
    
    console.print(tech_table)
    
    # Información de Traefik (referencia secundaria)
    if site_info.traefik_data:
        console.print("\n[bold]Configuración Traefik[/bold]")
        traefik_table = Table(show_header=False, box=None)
        traefik_table.add_column("Campo", style="cyan", width=20)
        traefik_table.add_column("Valor", style="dim")
        
        routers = site_info.traefik_data.get("http", {}).get("routers", {})
        services = site_info.traefik_data.get("http", {}).get("services", {})
        
        router_names = list(routers.keys())
        service_names = list(services.keys())
        
        if router_names:
            traefik_table.add_row("Routers", ", ".join(router_names[:3]))
        if service_names:
            traefik_table.add_row("Services", ", ".join(service_names[:3]))
        
        console.print(traefik_table)
        console.print("[dim]Nota: Esta es información de referencia. Los datos principales están arriba.[/dim]")
    
    # Health check (si está configurado)
    if site_info.manifest and site_info.manifest.health_check_enabled:
        console.print("\n[bold]Health Check[/bold]")
        health_table = Table(show_header=False, box=None)
        health_table.add_column("Campo", style="cyan", width=20)
        health_table.add_column("Valor", style="green")
        
        health_table.add_row("Estado", "[green]✅ Habilitado[/green]")
        if site_info.manifest.health_check_path:
            health_table.add_row("Path", site_info.manifest.health_check_path)
        
        console.print(health_table)
    
    console.print()
