"""
Wizard interactivo para crear configuración de servidor (servers add).
Genera archivos YAML en ~/.lsxtool/{provider}/servers/{service}/{env}/{target}-{name}.yml

Servicios, targets y environments se leen de ~/.lsxtool/config/{provider_id}.yaml
(capabilities.servers_web). No se usan valores hardcodeados.
"""

import yaml
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from .sync_routes import SYNC_ROUTES
from .provider_config import (
    load_provider_config,
    get_servers_web_capability,
    get_provider_config_path,
    MissingCapabilityError,
)


def load_providers_catalog(catalog_path: Path) -> list[dict]:
    """Carga la lista de providers desde el catálogo YAML (proyecto o home)."""
    if not catalog_path.exists():
        return []
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("providers", [])
    except Exception:
        return []


def prompt_provider(console: Console, catalog_path: Path) -> Optional[str]:
    """Pide al usuario seleccionar un provider desde el catálogo."""
    providers = load_providers_catalog(catalog_path)
    if not providers:
        console.print("[yellow]⚠ No se encontraron providers en el catálogo[/yellow]")
        return Prompt.ask("Ingresa el ID del provider", default="lunarsystemx")

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
    selected = providers[int(choice) - 1]
    return selected.get("id")


def ensure_servers_web_capability(provider_id: str, console: Console) -> dict:
    """
    Carga la config del provider y devuelve capabilities.servers_web.
    Si no existe, muestra mensaje y sugiere lsxtool providers configure.
    """
    provider_config = load_provider_config(provider_id)
    if provider_config is None:
        config_path = get_provider_config_path(provider_id)
        console.print(f"[red]❌ No existe la configuración del provider [bold]{provider_id}[/bold].[/red]")
        console.print(f"  Archivo esperado: [dim]{config_path}[/dim]")
        console.print()
        console.print("[yellow]Opciones:[/yellow]")
        console.print("  • En [bold]desarrollo[/bold]: crea un [dim].env[/dim] con [cyan]LSXTOOL_DEV=1[/cyan] para usar la carpeta [dim].lsxtool/config[/dim] de este proyecto.")
        console.print("  • En [bold]producción[/bold] o para crear la config en tu home: ejecuta [cyan]lsxtool providers configure[/cyan]")
        console.print()
        raise MissingCapabilityError(provider_id, "config_file", config_path)

    servers_web = get_servers_web_capability(provider_config)
    if not servers_web:
        config_path = get_provider_config_path(provider_id)
        console.print(f"[yellow]⚠ El provider [bold]{provider_id}[/bold] no tiene definida la capacidad:[/yellow]")
        console.print("  [bold]capabilities.servers_web[/bold]")
        console.print()
        console.print("Para inicializarla ejecuta:")
        console.print("  [cyan]lsxtool providers configure[/cyan]")
        console.print()
        console.print(f"  (aparecerá la lista de providers; al seleccionar [bold]{provider_id}[/bold],")
        console.print("   podrás configurar 1-Servidor web, 2-Servidor base de datos, etc.)")
        console.print()
        raise MissingCapabilityError(provider_id, "servers_web", config_path)

    # Validar que tenga services, targets, environments
    services = servers_web.get("services") or []
    targets = servers_web.get("targets") or []
    environments = servers_web.get("environments") or []

    if not services:
        console.print("[red]❌ capabilities.servers_web.services está vacío en la configuración del provider.[/red]")
        console.print("  Edita el archivo o ejecuta: [cyan]lsxtool providers configure[/cyan]")
        raise MissingCapabilityError(provider_id, "servers_web.services", get_provider_config_path(provider_id))
    if not targets:
        console.print("[red]❌ capabilities.servers_web.targets está vacío en la configuración del provider.[/red]")
        console.print("  Edita el archivo o ejecuta: [cyan]lsxtool providers configure[/cyan]")
        raise MissingCapabilityError(provider_id, "servers_web.targets", get_provider_config_path(provider_id))
    if not environments:
        console.print("[red]❌ capabilities.servers_web.environments está vacío en la configuración del provider.[/red]")
        console.print("  Edita el archivo o ejecuta: [cyan]lsxtool providers configure[/cyan]")
        raise MissingCapabilityError(provider_id, "servers_web.environments", get_provider_config_path(provider_id))

    return servers_web


def prompt_service(console: Console, services: list[str]) -> str:
    """Pide al usuario seleccionar un servicio desde la lista del provider."""
    table = Table(title="Servicios disponibles", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Servicio", style="green")

    for i, svc in enumerate(services, 1):
        table.add_row(str(i), svc)

    console.print()
    console.print(table)

    choices = [str(i) for i in range(1, len(services) + 1)]
    choice = Prompt.ask("Selecciona un servicio", choices=choices, default="1")
    return services[int(choice) - 1]


def prompt_environment(console: Console, environments: list[str]) -> str:
    """Pide al usuario seleccionar o ingresar el entorno (sugerencias desde el provider)."""
    suggestions_str = ", ".join(environments)
    console.print(f"\n[dim]Sugerencias del provider: {suggestions_str}[/dim]")
    default = environments[0] if environments else "dev"
    return Prompt.ask("Entorno", default=default).strip()


def prompt_target(console: Console, targets: list[str]) -> str:
    """Pide al usuario seleccionar el tipo de target desde la lista del provider."""
    table = Table(title="Tipo de target", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Tipo", style="green")
    table.add_column("Descripción", style="dim")

    descriptions = {"host": "Filesystem local (ej: /etc/nginx)", "docker": "Contenedor Docker"}
    for i, t in enumerate(targets, 1):
        table.add_row(str(i), t, descriptions.get(t, ""))

    console.print()
    console.print(table)

    choices = [str(i) for i in range(1, len(targets) + 1)]
    choice = Prompt.ask("Selecciona el tipo de target", choices=choices, default="1")
    return targets[int(choice) - 1]


def prompt_docker_config(console: Console) -> dict:
    """Pide configuración adicional para target docker."""
    console.print("\n[cyan]Configuración Docker[/cyan]")
    container = Prompt.ask("Nombre del contenedor", default="")
    if not container:
        console.print("[red]❌ El nombre del contenedor es requerido[/red]")
        raise ValueError("Container name required")

    base_path = Prompt.ask("Ruta base dentro del contenedor", default="/etc/nginx")

    pre_sync_cmd = Prompt.ask(
        "Comando de validación previo (opcional, ej: nginx -t)",
        default="",
        show_default=False,
    ).strip()

    reload_cmd = Prompt.ask(
        "Comando de recarga (opcional, ej: docker exec <container> nginx -s reload)",
        default="",
        show_default=False,
    ).strip()

    return {
        "container": container,
        "base_path": base_path,
        "pre_sync_cmd": pre_sync_cmd if pre_sync_cmd else None,
        "reload_cmd": reload_cmd if reload_cmd else None,
    }


def prompt_server_name(console: Console, service: str, environment: str, target: str) -> str:
    """Pide o genera un nombre para el servidor."""
    default_name = f"{target}-{service}-{environment}"
    name = Prompt.ask("Nombre del servidor (para el archivo)", default=default_name).strip()
    return name


# Modos de servidor: import = ya existe, descubrir; managed = lsxtool controla; bootstrap = vacío
SERVER_MODES = [
    ("import", "Importar servidor existente (descubrir rutas)"),
    ("managed", "Crear servidor gestionado por lsxtool (rutas estándar)"),
    ("bootstrap", "Servidor vacío / bootstrap"),
]


def prompt_server_mode(console: Console) -> str:
    """Pide si el servidor ya existe (import) o será gestionado (managed/bootstrap)."""
    table = Table(
        title="¿Este servidor ya existe o es nuevo?",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="cyan", width=4)
    table.add_column("Modo", style="green")
    table.add_column("Descripción", style="dim")

    for i, (mode_id, desc) in enumerate(SERVER_MODES, 1):
        table.add_row(str(i), mode_id, desc)

    console.print()
    console.print(table)

    choices = [str(i) for i in range(1, len(SERVER_MODES) + 1)]
    choice = Prompt.ask("Selecciona el modo", choices=choices, default="1")
    return SERVER_MODES[int(choice) - 1][0]


def prompt_import_discovery(console: Console, service: str, target_type: str) -> dict | None:
    """
    En modo import, pregunta si escanear automáticamente (ej. nginx -T).
    Devuelve {'method': 'auto'|'manual', 'command': str|None} o None si no aplica.
    """
    if target_type != "host":
        return {"method": "manual"}

    if service == "nginx":
        console.print("\n[cyan]Detección de rutas (modo import)[/cyan]")
        if Confirm.ask("¿Escanear includes con 'nginx -T' para proponer rutas?", default=True):
            return {"method": "auto", "command": "nginx -T"}
        return {"method": "manual"}
    if service == "apache":
        console.print("\n[cyan]Detección de rutas (modo import)[/cyan]")
        if Confirm.ask("¿Escanear con 'apachectl -S' para proponer rutas?", default=True):
            return {"method": "auto", "command": "apachectl -S"}
        return {"method": "manual"}
    return {"method": "manual"}


def collect_wizard_data(base_dir: Path, console: Console) -> dict:
    """Ejecuta el wizard completo. Usa capabilities.servers_web del provider."""
    console.print(Panel.fit("[bold cyan]Crear Configuración de Servidor[/bold cyan]", border_style="cyan"))

    # 1. Provider (desde catálogo)
    catalog_path = base_dir / ".lsxtool" / "catalog" / "providers.yaml"
    provider = prompt_provider(console, catalog_path)
    if not provider:
        raise ValueError("Provider requerido")

    # 2. Cargar config del provider y exigir capabilities.servers_web
    servers_web = ensure_servers_web_capability(provider, console)
    services = servers_web["services"]
    targets = servers_web["targets"]
    environments = servers_web["environments"]

    # 3. Servicio (desde provider)
    service = prompt_service(console, services)

    # 4. Modo: import (existente) vs managed/bootstrap (nuevo)
    mode = prompt_server_mode(console)

    # 5. Entorno (desde provider)
    environment = prompt_environment(console, environments)

    # 6. Target (desde provider)
    target_type = prompt_target(console, targets)

    # 7. Configuración del target
    target_config = {"type": target_type}
    docker_config = {}

    if target_type == "docker":
        docker_config = prompt_docker_config(console)
        target_config.update(
            {
                "container": docker_config["container"],
                "base_path": docker_config["base_path"],
            }
        )

    # 8. Discovery (solo en modo import): escanear con nginx -T / apachectl -S
    discovery = None
    if mode == "import":
        discovery = prompt_import_discovery(console, service, target_type)

    # 9. Nombre del servidor
    server_name = prompt_server_name(console, service, environment, target_type)

    # 10. Comandos opcionales
    pre_sync = []
    reload_cmd = None

    if target_type == "docker":
        if docker_config.get("pre_sync_cmd"):
            pre_sync = [docker_config["pre_sync_cmd"]]
        if docker_config.get("reload_cmd"):
            reload_cmd = docker_config["reload_cmd"]
    else:
        if Confirm.ask("\n¿Configurar comandos opcionales (validación/recarga)?", default=False):
            pre_sync_input = Prompt.ask(
                "Comando de validación previo (opcional, ej: nginx -t)",
                default="",
                show_default=False,
            ).strip()
            if pre_sync_input:
                pre_sync = [pre_sync_input]

            reload_input = Prompt.ask(
                "Comando de recarga (opcional, ej: systemctl reload nginx)",
                default="",
                show_default=False,
            ).strip()
            if reload_input:
                reload_cmd = reload_input

    return {
        "provider": provider,
        "service": service,
        "environment": environment,
        "mode": mode,
        "discovery": discovery,
        "target": target_config,
        "server_name": server_name,
        "pre_sync": pre_sync if pre_sync else None,
        "reload_cmd": reload_cmd,
    }
