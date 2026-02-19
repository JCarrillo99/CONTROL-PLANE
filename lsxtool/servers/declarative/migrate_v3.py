#!/usr/bin/env python3
"""
Migración v3: convierte YAML sites de routes dict → lista con name.
Convierte upstreams de runtime/tech simples → nodes[] opcional.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console
from rich.prompt import Confirm

try:
    from .convention_v2 import get_declarative_root
except ImportError:
    from convention_v2 import get_declarative_root


def _migrate_site_routes_to_list(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte routes de dict a lista con name y uri completo."""
    routes = data.get("routes")
    if routes is None:
        data["routes"] = []
        return data
    
    # Ya es lista → verificar que tiene name y uri
    if isinstance(routes, list):
        migrated = []
        for route in routes:
            if not isinstance(route, dict):
                continue
            # Si no tiene name, generarlo
            if "name" not in route:
                uri = route.get("uri", {})
                public = uri.get("public", "/") if isinstance(uri, dict) else "/"
                name = public.strip("/").replace("/", "_").replace("-", "_")
                route["name"] = name if name else "root"
            # Si no tiene uri, crearlo
            if "uri" not in route:
                route["uri"] = {
                    "public": "/",
                    "upstream": "/",
                    "strategy": "passthrough",
                }
            migrated.append(route)
        data["routes"] = migrated
        return data
    
    # Es dict → convertir a lista
    if isinstance(routes, dict):
        converted = []
        for path_key, route_data in routes.items():
            if not isinstance(route_data, dict):
                continue
            
            # Generar name desde path
            name = path_key.strip("/").replace("/", "_").replace("-", "_")
            if not name:
                name = "root"
            
            # Obtener o crear uri
            uri_data = route_data.get("uri")
            if not uri_data:
                strategy = "passthrough" if path_key == "/" else "strip"
                uri_data = {
                    "public": path_key,
                    "upstream": "/",
                    "strategy": strategy,
                }
            
            converted.append({
                "name": name,
                "type": route_data.get("type", "proxy"),
                "upstream_ref": route_data.get("upstream_ref", ""),
                "uri": uri_data,
            })
        
        data["routes"] = converted
    
    return data


def migrate_site_yaml(site_path: Path, console: Console, dry_run: bool = False) -> bool:
    """Migra un site YAML al nuevo formato (routes lista)."""
    if not site_path.exists():
        return False
    
    with open(site_path, "r") as f:
        data = yaml.safe_load(f) or {}
    
    original = yaml.dump(data, default_flow_style=False, sort_keys=False)
    
    # Migrar routes
    data = _migrate_site_routes_to_list(data)
    
    migrated = yaml.dump(data, default_flow_style=False, sort_keys=False)
    
    if original == migrated:
        console.print(f"  [dim]{site_path.name} ya migrado[/dim]")
        return False
    
    console.print(f"  [cyan]{site_path.name}[/cyan] → routes como lista con name")
    
    if dry_run:
        console.print(f"    [yellow]Dry-run: no se escribe[/yellow]")
        return True
    
    with open(site_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    console.print(f"    [green]✅ Migrado[/green]")
    return True


def migrate_upstream_yaml(upstream_path: Path, console: Console, dry_run: bool = False) -> bool:
    """
    Migra upstream YAML: si tiene runtime/tech simples, los mantiene (retrocompat).
    Solo reporta si el formato es legacy o v3.
    """
    if not upstream_path.exists():
        return False
    
    with open(upstream_path, "r") as f:
        data = yaml.safe_load(f) or {}
    
    up = data.get("upstream", {})
    
    has_nodes = "nodes" in up
    has_runtime = "runtime" in up
    
    if has_nodes:
        console.print(f"  [dim]{upstream_path.name} formato v3 (nodes)[/dim]")
    elif has_runtime:
        console.print(f"  [dim]{upstream_path.name} formato simple (runtime)[/dim]")
    
    return False


def migrate_all(
    base_dir: Path,
    console: Optional[Console] = None,
    dry_run: bool = False,
    confirm: bool = True,
) -> int:
    """
    Migra todos los sites y upstreams al nuevo formato.
    """
    console = console or Console()
    root = get_declarative_root(base_dir) / "providers"
    if not root.exists():
        console.print("[yellow]No hay providers en .lsxtool/providers/[/yellow]")
        return 0
    
    # Sites
    sites_paths = []
    for pdir in root.rglob("sites"):
        if pdir.is_dir():
            sites_paths.extend(pdir.glob("*.yaml"))
    
    # Upstreams
    upstream_paths = []
    for pdir in root.rglob("upstreams"):
        if pdir.is_dir():
            upstream_paths.extend(pdir.glob("*.yaml"))
    
    console.print(f"[bold cyan]Migración v3: {len(sites_paths)} site(s), {len(upstream_paths)} upstream(s)[/bold cyan]")
    
    if confirm and not dry_run:
        if not Confirm.ask("¿Continuar con la migración?", default=True):
            console.print("[yellow]Cancelado[/yellow]")
            return 0
    
    count = 0
    
    console.print("\n[bold]Sites:[/bold]")
    for sp in sites_paths:
        if migrate_site_yaml(sp, console, dry_run):
            count += 1
    
    console.print("\n[bold]Upstreams:[/bold]")
    for up in upstream_paths:
        migrate_upstream_yaml(up, console, dry_run)
    
    console.print(f"\n[bold green]✅ {count} archivo(s) migrado(s)[/bold green]")
    return count


if __name__ == "__main__":
    import sys
    base = Path.cwd()
    console = Console()
    dry = "--dry-run" in sys.argv
    migrate_all(base, console, dry_run=dry, confirm=not dry)
