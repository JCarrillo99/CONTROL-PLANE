"""
Comando providers: listar y configurar providers (capabilities).
"""

import yaml
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

# Importar desde servers (donde está la lógica de provider config)
try:
    from servers.cli_modules.provider_config import (
        get_config_dir,
        get_lsxtool_base_dir,
        get_provider_config_path,
        load_provider_config,
        get_capability_label,
        CAPABILITY_LABELS,
    )
except ImportError:
    from lsxtool.servers.cli_modules.provider_config import (
        get_config_dir,
        get_lsxtool_base_dir,
        get_provider_config_path,
        load_provider_config,
        get_capability_label,
        CAPABILITY_LABELS,
    )

app = typer.Typer(
    name="providers",
    help="Configuración de providers y capacidades (~/.lsxtool/config)",
    add_completion=False,
)
console = Console()


def find_catalog_path() -> Optional[Path]:
    """Busca providers.yaml: primero en proyecto (cwd/padres), luego en ~/.lsxtool/catalog."""
    # Proyecto: .lsxtool/catalog/providers.yaml
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        catalog = parent / ".lsxtool" / "catalog" / "providers.yaml"
        if catalog.exists():
            return catalog
    # Home
    home_catalog = Path.home() / ".lsxtool" / "catalog" / "providers.yaml"
    if home_catalog.exists():
        return home_catalog
    return None


def load_providers_from_catalog() -> list[dict]:
    """Carga la lista de providers desde el catálogo."""
    path = find_catalog_path()
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("providers", [])
    except Exception:
        return []


# Capacidades conocidas que se pueden configurar (orden de menú)
CONFIGURABLE_CAPABILITIES = ["servers_web", "servers_database"]


# Plantilla por capacidad (para inicializar si falta)
CAPABILITY_TEMPLATES = {
    "servers_web": {
        "services": ["nginx", "apache", "traefik", "caddy"],
        "targets": ["host", "docker"],
        "environments": ["dev", "qa", "prod"],
    },
    "servers_database": {
        "services": [
            "postgres",
            "mysql",
            "redis",
            "mongodb",
            "elasticsearch",
            "kafka",
            "rabbitmq",
            "minio",
        ],
    },
}


def _list_configured_provider_ids() -> list[str]:
    """IDs de providers que tienen config en .lsxtool/config/*.yaml."""
    config_dir = get_config_dir()
    if not config_dir.exists():
        return []
    return sorted(
        p.stem for p in config_dir.glob("*.yaml")
        if p.stem and not p.name.startswith(".")
    )


@app.command()
def add(
    provider_id: Optional[str] = typer.Argument(None, help="ID del provider (ej: lunarsystemx)"),
):
    """
    Registrar un provider y crear su archivo de config.
    Si se omite el ID, se elige de la lista del catálogo o se pide uno nuevo.
    """
    console.print(Panel.fit("[bold cyan]Alta de Provider[/bold cyan]", border_style="cyan"))

    providers_catalog = load_providers_from_catalog()
    if not provider_id:
        if providers_catalog:
            table = Table(title="Providers en el catálogo", show_header=True, header_style="bold cyan")
            table.add_column("#", style="cyan", width=4)
            table.add_column("ID", style="green")
            table.add_column("Nombre", style="yellow")
            for i, p in enumerate(providers_catalog, 1):
                table.add_row(str(i), p.get("id", ""), p.get("name", ""))
            console.print(table)
            console.print("  0) Crear uno nuevo (pedir ID)")
            choices = [str(i) for i in range(0, len(providers_catalog) + 1)]
            choice = Prompt.ask("Selecciona o 0 para nuevo", choices=choices, default="1")
            if choice != "0":
                provider_id = providers_catalog[int(choice) - 1].get("id")
        if not provider_id:
            provider_id = Prompt.ask("ID del provider").strip()
    if not provider_id:
        console.print("[red]Se requiere un ID.[/red]")
        raise SystemExit(1)

    # Datos del catálogo si existe
    existing = next((p for p in (providers_catalog or []) if p.get("id") == provider_id), None)
    name = (existing and existing.get("name")) or provider_id
    domain_suffix = (existing and existing.get("domain_suffix")) or ""
    internal_namespace = (existing and existing.get("internal_namespace")) or ""

    config_path = get_provider_config_path(provider_id)
    if config_path.exists():
        console.print(f"[yellow]El provider [bold]{provider_id}[/bold] ya tiene config.[/yellow]")
        console.print(f"  [dim]{config_path}[/dim]")
        if not Confirm.ask("¿Sobrescribir?", default=False):
            raise SystemExit(0)

    # Elegir capacidades a habilitar
    console.print()
    console.print("[bold]¿Qué capacidades habilitar?[/bold]")
    for i, cap_key in enumerate(CONFIGURABLE_CAPABILITIES, 1):
        console.print(f"  {i}) {get_capability_label(cap_key)}")
    console.print("  0) Ninguna (solo estructura base)")
    raw = Prompt.ask("Números separados por coma", default="1").strip()
    capabilities = {}
    if raw and raw != "0":
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(CONFIGURABLE_CAPABILITIES):
                    cap_key = CONFIGURABLE_CAPABILITIES[idx - 1]
                    capabilities[cap_key] = CAPABILITY_TEMPLATES.get(cap_key, {})

    current = {
        "provider": {
            "id": provider_id,
            "name": name,
            "domain_suffix": domain_suffix,
            "internal_namespace": internal_namespace,
        },
        "capabilities": capabilities,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    console.print(f"\n[green]✓ Configuración guardada[/green]")
    console.print(f"  [dim]{config_path}[/dim]")
    console.print()
    console.print("[dim]Ajusta capacidades con: lsxtool providers configure[/dim]")


@app.command()
def view(
    provider_id: Optional[str] = typer.Argument(None, help="ID del provider (si se omite, se elige de la lista)"),
):
    """
    Ver providers configurados y sus capacidades.
    Muestra la lista, permite elegir uno y ver detalle (Config: ruta del archivo).
    """
    configured_ids = _list_configured_provider_ids()
    if not configured_ids:
        console.print("[yellow]No hay providers configurados.[/yellow]")
        console.print("  [dim]Añade uno con: lsxtool providers add[/dim]")
        raise SystemExit(0)

    if not provider_id:
        console.print(Panel.fit("[bold cyan]Providers configurados[/bold cyan]", border_style="cyan"))
        for i, pid in enumerate(configured_ids, 1):
            console.print(f"  {i}) {pid}")
        choices = [str(i) for i in range(1, len(configured_ids) + 1)]
        choice = Prompt.ask("Selecciona un provider", choices=choices, default="1")
        provider_id = configured_ids[int(choice) - 1]

    config_path = get_provider_config_path(provider_id)
    current = load_provider_config(provider_id) or {}
    console.print()
    console.print(Panel.fit(f"[bold cyan]{provider_id}[/bold cyan]", border_style="cyan"))
    console.print(f"  [dim]Config:[/dim] {config_path}")
    caps = current.get("capabilities") or {}
    if caps:
        console.print("  [bold]Capacidades:[/bold]")
        for cap_key, cap_data in caps.items():
            label = get_capability_label(cap_key)
            if cap_data and isinstance(cap_data, dict):
                svc = cap_data.get("services") or []
                console.print(f"    - {label}: {', '.join(svc) if svc else '(vacío)'}")
            else:
                console.print(f"    - {label}")
    else:
        console.print("  [dim]Sin capacidades definidas.[/dim]")
    console.print()
    console.print("  1) Configurar este provider")
    console.print("  2) Nada")
    action = Prompt.ask("Elige", choices=["1", "2"], default="2")
    if action == "1":
        configure(provider_id)


@app.command()
def configure(
    provider_id: Optional[str] = typer.Argument(None, help="ID del provider (si se omite, se elige de la lista)"),
):
    """
    Configura las capacidades de un provider.
    Muestra la lista de providers; al seleccionar uno, permite configurar
    1-Servidor web, 2-Servidor base de datos, etc.
    La configuración se guarda en ~/.lsxtool/config/{provider_id}.yaml
    """
    console.print(Panel.fit("[bold cyan]Configurar Provider[/bold cyan]", border_style="cyan"))

    # 1. Obtener provider_id
    if not provider_id:
        providers = load_providers_from_catalog()
        if not providers:
            console.print("[yellow]⚠ No se encontró el catálogo de providers.[/yellow]")
            console.print("  Crea [dim]~/.lsxtool/catalog/providers.yaml[/dim] o [dim].lsxtool/catalog/providers.yaml[/dim] en el proyecto.")
            console.print("  Ejemplo:")
            console.print("    [dim]providers:\\n  - id: lunarsystemx\\n    name: Lunar System X[/dim]")
            raise SystemExit(1)

        table = Table(title="Providers disponibles", show_header=True, header_style="bold cyan")
        table.add_column("#", style="cyan", width=4)
        table.add_column("ID", style="green")
        table.add_column("Nombre", style="yellow")
        for i, p in enumerate(providers, 1):
            table.add_row(str(i), p.get("id", ""), p.get("name", ""))
        console.print()
        console.print(table)
        choices = [str(i) for i in range(1, len(providers) + 1)]
        choice = Prompt.ask("Selecciona un provider", choices=choices, default="1")
        provider_id = providers[int(choice) - 1].get("id")
        if not provider_id:
            console.print("[red]Provider sin ID[/red]")
            raise SystemExit(1)

    # 2. Cargar config actual o plantilla base
    config_path = get_provider_config_path(provider_id)
    current = load_provider_config(provider_id) or {}

    # Asegurar estructura mínima
    if "provider" not in current:
        current["provider"] = {
            "id": provider_id,
            "name": provider_id,
            "domain_suffix": "",
            "internal_namespace": "",
        }
    if "capabilities" not in current:
        current["capabilities"] = {}

    # 3. Menú de capacidades
    table = Table(title="Capacidades a configurar", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Capacidad", style="green")
    table.add_column("Estado", style="dim")
    for i, cap_key in enumerate(CONFIGURABLE_CAPABILITIES, 1):
        label = get_capability_label(cap_key)
        has_cap = (current.get("capabilities") or {}).get(cap_key) not in (None, {})
        status = "✓ Definida" if has_cap else "— No definida"
        table.add_row(str(i), label, status)
    console.print()
    console.print(table)
    choices = [str(i) for i in range(1, len(CONFIGURABLE_CAPABILITIES) + 1)]
    choice = Prompt.ask("Selecciona la capacidad a configurar", choices=choices, default="1")
    cap_key = CONFIGURABLE_CAPABILITIES[int(choice) - 1]

    # 4. Aplicar plantilla si no existe
    template = CAPABILITY_TEMPLATES.get(cap_key)
    if template and not (current.get("capabilities") or {}).get(cap_key):
        current.setdefault("capabilities", {})[cap_key] = template
        console.print(f"[green]✓ Plantilla de [bold]{get_capability_label(cap_key)}[/bold] añadida.[/green]")
    elif (current.get("capabilities") or {}).get(cap_key):
        console.print(f"[dim]La capacidad [bold]{cap_key}[/bold] ya está definida. Edita el archivo para cambiarla.[/dim]")
    else:
        current.setdefault("capabilities", {})[cap_key] = {}

    # 5. Guardar
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    console.print(f"\n[green]✓ Configuración guardada[/green]")
    console.print(f"  [dim]{config_path}[/dim]")
    console.print()
    console.print("[dim]Puedes editar el archivo para ajustar services, targets y environments.[/dim]")
