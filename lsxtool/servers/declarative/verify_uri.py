#!/usr/bin/env python3
"""
Verificador de transformación URI: comprueba que las rutas se transformen correctamente.
Muestra ejemplos de cómo NGINX transformará las URIs según strategy.
"""

from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from rich.console import Console
from rich.table import Table

try:
    from .convention_v2 import get_declarative_root
except ImportError:
    from convention_v2 import get_declarative_root


def verify_site(site_path: Path, console: Console) -> None:
    """Verifica un site YAML y muestra ejemplos de transformación."""
    with open(site_path, "r") as f:
        data = yaml.safe_load(f)
    
    domain = data.get("domain", site_path.stem)
    routes = data.get("routes", {})
    
    console.print(f"\n[bold cyan]Site: {domain}[/bold cyan]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Public Path", style="cyan")
    table.add_column("Strategy", style="yellow")
    table.add_column("Upstream Path", style="green")
    table.add_column("Ejemplo Request → Backend")
    
    for public, route_data in routes.items():
        if not isinstance(route_data, dict):
            continue
        
        uri = route_data.get("uri", {})
        if not uri:
            table.add_row(
                public,
                "[red]❌ Sin uri[/red]",
                "-",
                "[red]Migrar con migrate_uri.py[/red]"
            )
            continue
        
        public_path = uri.get("public", public)
        upstream_path = uri.get("upstream", "/")
        strategy = uri.get("strategy", "strip")
        upstream_ref = route_data.get("upstream_ref", "?")
        
        # Ejemplos de transformación
        if strategy == "strip":
            examples = [
                (f"{public_path}", f"{upstream_path}"),
                (f"{public_path}auth", f"{upstream_path}auth"),
                (f"{public_path}users/123", f"{upstream_path}users/123"),
            ]
        else:  # passthrough
            examples = [
                (f"{public_path}", f"{upstream_path}"),
                (f"{public_path}auth", f"{upstream_path}auth"),
            ]
        
        example_str = "\n".join([f"[dim]{req}[/dim] → [bold]{backend}[/bold]" for req, backend in examples])
        
        table.add_row(
            public_path,
            f"[yellow]{strategy}[/yellow]",
            upstream_path,
            example_str
        )
    
    console.print(table)


def verify_all(base_dir: Path, console: Console) -> None:
    """Verifica todos los sites YAML."""
    root = get_declarative_root(base_dir) / "providers"
    if not root.exists():
        console.print("[yellow]No hay providers en .lsxtool/providers/[/yellow]")
        return
    
    sites_paths = []
    for pdir in root.rglob("sites"):
        if pdir.is_dir():
            sites_paths.extend(pdir.glob("*.yaml"))
    
    if not sites_paths:
        console.print("[dim]No se encontraron sites YAML[/dim]")
        return
    
    for sp in sites_paths:
        verify_site(sp, console)


if __name__ == "__main__":
    base = Path.cwd()
    console = Console()
    verify_all(base, console)
