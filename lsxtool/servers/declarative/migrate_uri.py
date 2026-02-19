"""
Migración automática: configs existentes sin uri → añadir uri con strategy strip.
Lee YAMLs de sites/, detecta routes sin uri, infiere uri.public=path_key, uri.upstream=/, uri.strategy=strip.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import yaml

from rich.console import Console
from rich.prompt import Confirm

try:
    from .convention_v2 import get_declarative_root
    from .models_v2 import FrontendDomainConfig, RouteConfig, UriTransformConfig
except ImportError:
    from convention_v2 import get_declarative_root
    from models_v2 import FrontendDomainConfig, RouteConfig, UriTransformConfig


def migrate_site_yaml(site_path: Path, console: Optional[Console] = None, dry_run: bool = False) -> bool:
    """
    Lee un site YAML, detecta routes sin uri, añade uri inferido.
    Inferencia: public=path_key, upstream=/, strategy=strip (comportamiento anterior).
    Para "/" usa strategy=passthrough y upstream=/.
    """
    console = console or Console()
    if not site_path.exists():
        console.print(f"[yellow]⚠ {site_path} no existe[/yellow]")
        return False
    
    with open(site_path, "r") as f:
        data = yaml.safe_load(f)
    
    if not data or "routes" not in data:
        console.print(f"[dim]Sin routes en {site_path.name}[/dim]")
        return False
    
    routes = data.get("routes", {})
    modified = False
    
    for path_key, route_data in routes.items():
        if not isinstance(route_data, dict):
            continue
        if "uri" in route_data:
            continue  # ya tiene uri
        
        # Inferir uri
        if path_key == "/":
            uri_inferred = {
                "public": "/",
                "upstream": "/",
                "strategy": "passthrough",
            }
        else:
            uri_inferred = {
                "public": path_key,
                "upstream": "/",
                "strategy": "strip",
            }
        
        route_data["uri"] = uri_inferred
        modified = True
        console.print(
            f"  [cyan]{site_path.name}[/cyan] route [bold]{path_key}[/bold] → "
            f"uri(public={uri_inferred['public']}, upstream={uri_inferred['upstream']}, strategy={uri_inferred['strategy']})"
        )
    
    if not modified:
        console.print(f"[dim]{site_path.name} ya tiene uri en todas las routes[/dim]")
        return False
    
    if dry_run:
        console.print(f"[yellow]Dry-run: no se escribe {site_path.name}[/yellow]")
        return True
    
    # Reescribir YAML
    with open(site_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    console.print(f"[green]✅ {site_path.name} actualizado[/green]")
    return True


def migrate_all_sites(
    base_dir: Path,
    console: Optional[Console] = None,
    dry_run: bool = False,
    confirm: bool = True,
) -> int:
    """
    Busca todos los sites YAML en providers/.../sites/ y migra los que necesiten uri.
    Retorna cantidad de archivos modificados.
    """
    console = console or Console()
    root = get_declarative_root(base_dir) / "providers"
    if not root.exists():
        console.print("[yellow]No hay providers en .lsxtool/providers/[/yellow]")
        return 0
    
    sites_paths = []
    for pdir in root.rglob("sites"):
        if pdir.is_dir():
            sites_paths.extend(pdir.glob("*.yaml"))
    
    if not sites_paths:
        console.print("[dim]No se encontraron sites YAML[/dim]")
        return 0
    
    console.print(f"[bold cyan]Migración URI: {len(sites_paths)} site(s) encontrado(s)[/bold cyan]")
    
    if confirm and not dry_run:
        if not Confirm.ask("¿Continuar con la migración?", default=True):
            console.print("[yellow]Cancelado[/yellow]")
            return 0
    
    count = 0
    for sp in sites_paths:
        if migrate_site_yaml(sp, console, dry_run):
            count += 1
    
    console.print(f"\n[bold green]✅ {count} site(s) migrado(s)[/bold green]")
    return count


if __name__ == "__main__":
    import sys
    base = Path.cwd()
    console = Console()
    dry = "--dry-run" in sys.argv
    migrate_all_sites(base, console, dry_run=dry, confirm=not dry)
