#!/usr/bin/env python3
"""
Módulo de Servidores - LSX Tool
Gestión de servidores web (Nginx, Apache, Traefik)
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from typing import Optional, Literal
import subprocess
import sys
import os
from pathlib import Path

# Importar módulos locales
from .cli_modules.sync import sync_configs
from .cli_modules.server_config import list_configured_servers
from .cli_modules.site_creator import create_site
from .cli_modules.server_add import collect_wizard_data
from .cli_modules.server_config import (
    generate_yaml_config,
    write_config_file,
    get_config_path,
    run_import_discovery_and_create_workspace,
)
from .cli_modules.provider_config import MissingCapabilityError, list_configured_provider_ids
from .mount.cli import app as mount_app
from .declarative.upstream_cli import app as upstream_app

app = typer.Typer(
    name="servers",
    help="Gestión de Servidores Web (Nginx, Apache, Traefik)",
    add_completion=False
)
console = Console()

# Registrar submódulos
app.add_typer(mount_app, name="mount", help="Gestión de montajes de sistemas de archivos")
app.add_typer(upstream_app, name="upstream", help="Catálogo de upstreams declarativos (.lsxtool/upstreams/)")

# Obtener directorio base del módulo servers (donde están apache, nginx, traefik)
SERVERS_DIR = Path(__file__).parent.resolve()
# Directorio base del proyecto servers-install (para rutas absolutas del sistema)
BASE_DIR = SERVERS_DIR.parent.parent.resolve()


@app.command()
def status():
    """
    Muestra el estado de los servidores dados de alta (configurados en .lsxtool/providers/...).
    Solo se listan servidores registrados con 'lsxtool servers add'.
    """
    console.print(Panel.fit("[bold cyan]Estado de Servidores Web[/bold cyan]", border_style="cyan"))

    configured = list_configured_servers()
    if not configured:
        # Aun así preguntar de qué provider (de los configurados) quiere ver
        provider_ids = list_configured_provider_ids()
        if provider_ids:
            console.print("[bold]¿De qué provider quieres ver los servicios?[/bold] [dim](no hay servidores dados de alta aún)[/dim]")
            for i, pid in enumerate(provider_ids, 1):
                console.print(f"  {i}) {pid}")
            choices = [str(i) for i in range(1, len(provider_ids) + 1)]
            choice = Prompt.ask("Provider", choices=choices, default="1")
            selected_id = provider_ids[int(choice) - 1]
            console.print()
            console.print(f"[yellow]No hay servidores dados de alta para [bold]{selected_id}[/bold].[/yellow]")
            console.print("[dim]Para añadir uno:[/dim]")
            console.print("  [cyan]lsxtool providers configure[/cyan] → elige el provider y sincroniza/importa, o")
            console.print("  [cyan]lsxtool servers add[/cyan]")
            console.print("[dim]Luego sincroniza con: sudo lsxtool servers sync[/dim]")
        else:
            console.print("[yellow]No hay servidores dados de alta.[/yellow]")
            console.print("[dim]Configura un provider primero: lsxtool providers add[/dim]")
            console.print("[dim]Luego: lsxtool providers configure (y sincroniza) o lsxtool servers add[/dim]")
            console.print("[dim]Sincronizar: sudo lsxtool servers sync[/dim]")
        console.print()
        return

    # Si hay varios providers, preguntar de cuál ver los servicios
    providers = sorted({s["provider"] for s in configured})
    if len(providers) > 1:
        console.print("[bold]¿De qué provider quieres ver los servicios?[/bold]")
        for i, p in enumerate(providers, 1):
            console.print(f"  {i}) {p}")
        console.print(f"  {len(providers) + 1}) Todos")
        choices = [str(i) for i in range(1, len(providers) + 2)]
        choice = Prompt.ask("Provider", choices=choices, default="1")
        idx = int(choice)
        if idx <= len(providers):
            configured = [s for s in configured if s["provider"] == providers[idx - 1]]
        # si eligió "Todos", configured se queda como está
        console.print()

    # Servicios systemd por tipo (solo para los que tenemos configurados)
    systemd_names = {"traefik": "traefik", "apache": "apache2", "nginx": "nginx"}
    service_status_map = {}
    for sid in {s["service"] for s in configured}:
        name = systemd_names.get(sid, sid)
        try:
            r = subprocess.run(
                ["systemctl", "is-active", name],
                capture_output=True, text=True, check=False,
            )
            service_status_map[sid] = "✅ Activo" if r.returncode == 0 else "❌ Inactivo"
        except Exception:
            service_status_map[sid] = "❓"

    table = Table(
        title="Servidores dados de alta",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Provider", style="cyan")
    table.add_column("Servicio", style="green")
    table.add_column("Ambiente", style="yellow")
    table.add_column("Servidor", style="green")
    table.add_column("Estado", style="dim")
    for s in configured:
        st = service_status_map.get(s["service"], "—")
        table.add_row(
            s["provider"],
            s["service"],
            s["environment"],
            s["server_name"],
            st,
        )
    console.print(table)
    console.print()
    console.print("[dim]Sincronizar: sudo lsxtool servers sync[/dim]")
    console.print()


def _manage_site_meta(domain: str, console: Console):
    """Gestiona metadatos de un sitio (configurar/actualizar)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import get_site_info
    from servers.sites.meta_parser import parse_meta_from_conf, write_meta_to_conf, validate_meta
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    # Obtener información del sitio
    site_info = get_site_info(domain, BASE_DIR, console)
    
    if not site_info:
        console.print(f"[red]❌ Sitio '{domain}' no encontrado[/red]")
        console.print("[yellow]Usa 'lsxtool servers sites list' para ver sitios disponibles[/yellow]")
        return
    
    # Buscar archivo de configuración
    config_path = None
    if site_info.config_path and site_info.config_path != "N/A":
        config_path = Path(site_info.config_path)
        if not config_path.is_absolute():
            config_path = BASE_DIR / config_path
    else:
        # Buscar archivo de configuración
        apache_paths = [
            BASE_DIR / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
            BASE_DIR / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
        ]
        
        nginx_paths = [
            BASE_DIR / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            BASE_DIR / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
        ]
        
        for path in apache_paths + nginx_paths:
            if path.exists():
                config_path = path
                break
    
    if not config_path or not config_path.exists():
        console.print(f"[red]❌ No se encontró archivo de configuración para {domain}[/red]")
        return
    
    console.print(Panel.fit(f"[bold cyan]Gestión de Metadatos - {domain}[/bold cyan]", border_style="cyan"))
    
    # Leer metadatos actuales
    current_meta = parse_meta_from_conf(config_path)
    
    if current_meta:
        console.print("\n[bold]Metadatos actuales:[/bold]")
        meta_table = Table(show_header=False, box=None)
        meta_table.add_column("Campo", style="cyan", width=20)
        meta_table.add_column("Valor", style="green")
        
        for key, value in sorted(current_meta.items()):
            meta_table.add_row(key, value)
        
        console.print(meta_table)
    else:
        console.print("\n[yellow]⚠️ No hay metadatos configurados actualmente[/yellow]")
        current_meta = {}
    
    # Preguntar si actualizar
    if not Confirm.ask("\n¿Deseas actualizar los metadatos?", default=True):
        return
    
    # Importar catálogos
    from servers.sites.catalogs import (
        get_owners,
        get_providers,
        get_service_types,
        get_environments,
        get_backends,
        get_backend_versions
    )
    
    # Recopilar nuevos valores desde catálogos controlados
    console.print("\n[bold]Ingresa los metadatos desde catálogos controlados:[/bold]")
    
    # Owner desde catálogo
    owners_list = get_owners()
    console.print("\n[bold cyan]Equipos disponibles:[/bold cyan]")
    for idx, owner_item in enumerate(owners_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {owner_item}")
    
    owner_choice = Prompt.ask(
        "\n[bold]Selecciona Owner/Equipo responsable[/bold]",
        choices=[str(i) for i in range(1, len(owners_list) + 1)],
        default=str(1) if owners_list else None
    )
    owner = owners_list[int(owner_choice) - 1] if owner_choice else ""
    
    # Proveedor desde catálogo
    providers_list = get_providers()
    current_provider_idx = 0
    if current_meta.get("provider") in providers_list:
        current_provider_idx = providers_list.index(current_meta.get("provider")) + 1
    
    console.print("\n[bold cyan]Proveedores disponibles:[/bold cyan]")
    for idx, provider_item in enumerate(providers_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {provider_item}")
    
    provider_choice = Prompt.ask(
        "\n[bold]Selecciona Proveedor[/bold]",
        choices=[str(i) for i in range(1, len(providers_list) + 1)],
        default=str(current_provider_idx) if current_provider_idx > 0 else "1"
    )
    provider = providers_list[int(provider_choice) - 1]
    
    # Tipo de servicio desde catálogo
    service_types_list = get_service_types()
    current_service_type_idx = 0
    if current_meta.get("service_type") in service_types_list:
        current_service_type_idx = service_types_list.index(current_meta.get("service_type")) + 1
    
    console.print("\n[bold cyan]Tipos de servicio disponibles:[/bold cyan]")
    for idx, st_item in enumerate(service_types_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {st_item}")
    
    service_type_choice = Prompt.ask(
        "\n[bold]Selecciona Tipo de servicio[/bold]",
        choices=[str(i) for i in range(1, len(service_types_list) + 1)],
        default=str(current_service_type_idx) if current_service_type_idx > 0 else "1"
    )
    service_type = service_types_list[int(service_type_choice) - 1]
    
    # Ambiente desde catálogo
    environments_list = get_environments()
    current_env_idx = 0
    if current_meta.get("environment") in environments_list:
        current_env_idx = environments_list.index(current_meta.get("environment")) + 1
    
    console.print("\n[bold cyan]Ambientes disponibles:[/bold cyan]")
    for idx, env_item in enumerate(environments_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {env_item}")
    
    environment_choice = Prompt.ask(
        "\n[bold]Selecciona Ambiente[/bold]",
        choices=[str(i) for i in range(1, len(environments_list) + 1)],
        default=str(current_env_idx) if current_env_idx > 0 else "1"
    )
    environment = environments_list[int(environment_choice) - 1]
    
    # Backend desde catálogo
    backends_list = get_backends()
    current_backend = current_meta.get("backend", site_info.backend_type.lower())
    current_backend_idx = 0
    if current_backend in backends_list:
        current_backend_idx = backends_list.index(current_backend) + 1
    
    console.print("\n[bold cyan]Backends disponibles:[/bold cyan]")
    for idx, backend_item in enumerate(backends_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {backend_item}")
    
    backend_choice = Prompt.ask(
        "\n[bold]Selecciona Backend[/bold]",
        choices=[str(i) for i in range(1, len(backends_list) + 1)],
        default=str(current_backend_idx) if current_backend_idx > 0 else "1"
    )
    backend = backends_list[int(backend_choice) - 1]
    
    # Versión del backend - solo mostrar versiones disponibles
    backend_versions = get_backend_versions(backend)
    
    if backend_versions:
        console.print(f"\n[bold cyan]Versiones disponibles de {backend.upper()}:[/bold cyan]")
        for idx, version_item in enumerate(backend_versions, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {version_item}")
        
        current_version_idx = 0
        if current_meta.get("backend_version") in backend_versions:
            current_version_idx = backend_versions.index(current_meta.get("backend_version")) + 1
        
        version_choice = Prompt.ask(
            f"\n[bold]Selecciona Versión de {backend.upper()}[/bold]",
            choices=[str(i) for i in range(1, len(backend_versions) + 1)],
            default=str(current_version_idx) if current_version_idx > 0 else "1"
        )
        backend_version = backend_versions[int(version_choice) - 1]
    else:
        console.print(f"\n[yellow]⚠️ No se detectó versión de {backend.upper()} instalada[/yellow]")
        backend_version = Prompt.ask(
            f"Versión de {backend.upper()} (manual)",
            default=current_meta.get("backend_version", "")
        )
    
    # Construir dict de metadatos
    new_meta = {
        "owner": owner,
        "provider": provider,
        "service_type": service_type,
        "environment": environment,
        "backend": backend,
        "backend_version": backend_version
    }
    
    # Validar
    is_valid, warnings = validate_meta(new_meta, console)
    
    if warnings and not Confirm.ask("\n¿Continuar a pesar de las advertencias?", default=True):
        return
    
    # Escribir metadatos
    if write_meta_to_conf(config_path, new_meta, console):
        console.print(f"\n[bold green]✅ Metadatos actualizados para {domain}[/bold green]")
        console.print(f"[dim]Archivo: {config_path}[/dim]")
        
        # Mostrar resumen
        console.print("\n[bold]Metadatos actualizados:[/bold]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Campo", style="cyan", width=20)
        summary_table.add_column("Valor", style="green")
        
        for key, value in sorted(new_meta.items()):
            summary_table.add_row(key, value)
        
        console.print(summary_table)
        
        console.print(f"\n[yellow]💡 Ejecuta 'lsxtool servers sites info {domain}' para ver los cambios[/yellow]")
    else:
        console.print(f"\n[red]❌ Error al actualizar metadatos[/red]")
    
    console.print()


@app.command()
def verify(
    backend: Literal["nginx", "apache", "traefik"] = typer.Argument("nginx", help="Backend a verificar")
):
    """
    Verifica configuración de servidores web (validación avanzada de reglas LSX)
    
    Este comando NO reemplaza las validaciones de sintaxis (nginx -t, apache2ctl configtest),
    sino que las complementa con validaciones de reglas de negocio, estructura, naming y coherencia semántica.
    
    Ejemplos:
        lsxtool servers verify nginx    # Verificar configuración Nginx
        lsxtool servers verify apache   # Verificar configuración Apache (próximamente)
        lsxtool servers verify traefik # Verificar configuración Traefik (próximamente)
    """
    console.print(Panel.fit(f"[bold cyan]Verificación de {backend.upper()}[/bold cyan]", border_style="cyan"))
    
    if backend == "nginx":
        _verify_nginx(console)
    elif backend == "apache":
        console.print("[yellow]⚠️ Verificación de Apache aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")
    elif backend == "traefik":
        console.print("[yellow]⚠️ Verificación de Traefik aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")


@app.command()
def inspect(
    backend: Literal["nginx", "apache", "traefik"] = typer.Argument("nginx", help="Backend a inspeccionar"),
    domain: str = typer.Argument(..., help="Dominio a inspeccionar")
):
    """
    Inspecciona configuración de un dominio específico de forma interactiva
    
    Muestra checklist numerado de validaciones y permite ver detalles de cada check.
    Solo lectura, no modifica archivos.
    
    Ejemplos:
        lsxtool servers inspect nginx dev-identity.lunarsystemx.com
        lsxtool servers inspect apache dev-recibonomina.yucatan.gob.mx
    """
    console.print(Panel.fit(f"[bold cyan]Inspección de {backend.upper()} - {domain}[/bold cyan]", border_style="cyan"))
    
    if backend == "nginx":
        _inspect_nginx(domain, console)
    elif backend == "apache":
        console.print("[yellow]⚠️ Inspección de Apache aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")
    elif backend == "traefik":
        console.print("[yellow]⚠️ Inspección de Traefik aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")


@app.command()
def fix(
    backend: Literal["nginx", "apache", "traefik"] = typer.Argument("nginx", help="Backend a corregir"),
    domain: str = typer.Argument(..., help="Dominio a corregir")
):
    """
    Corrige problemas en la configuración de un dominio de forma guiada
    
    Solo habilitado si hay WARNINGS o ERRORS. Permite seleccionar checks a corregir.
    Crea backups automáticos y muestra diffs antes de aplicar cambios.
    
    Ejemplos:
        lsxtool servers fix nginx dev-identity.lunarsystemx.com
        lsxtool servers fix apache dev-recibonomina.yucatan.gob.mx
    """
    console.print(Panel.fit(f"[bold cyan]Corrección de {backend.upper()} - {domain}[/bold cyan]", border_style="cyan"))
    
    if backend == "nginx":
        _fix_nginx(domain, console)
    elif backend == "apache":
        console.print("[yellow]⚠️ Corrección de Apache aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")
    elif backend == "traefik":
        console.print("[yellow]⚠️ Corrección de Traefik aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")


@app.command()
def bootstrap(
    backend: Literal["nginx", "apache", "traefik"] = typer.Argument("nginx", help="Backend a configurar"),
    domain: str = typer.Argument(..., help="Dominio a configurar"),
    v2: bool = typer.Option(False, "--v2", help="Usar bootstrap v2 (frontends, routes, upstreams declarativos)"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Sin prompts; falla si faltan datos o upstreams inexistentes"),
):
    """
    Completa campos META obligatorios faltantes (modo PATCH).
    
    Si el bloque META ya existe pero faltan tech_provider/tech_manager, solo
    solicita esos campos. Si no existe META, guía para crearlo completo.
    Para reconfigurar TODOS los campos usa: reconfigure
    
    Con --v2: frontends, routes por path, upstreams en catálogo (formato v2).
    """
    console.print(Panel.fit(f"[bold cyan]Bootstrap de {backend.upper()} - {domain}[/bold cyan]", border_style="cyan"))
    
    if backend == "nginx":
        if v2:
            _bootstrap_nginx_v2(domain, console, full_reconfigure=False, non_interactive=non_interactive)
        else:
            _bootstrap_nginx(domain, console, full_reconfigure=False)
    elif backend == "apache":
        console.print("[yellow]⚠️ Bootstrap de Apache aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")
    elif backend == "traefik":
        console.print("[yellow]⚠️ Bootstrap de Traefik aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")


@app.command()
def reconfigure(
    backend: Literal["nginx", "apache", "traefik"] = typer.Argument("nginx", help="Backend a reconfigurar"),
    domain: str = typer.Argument(..., help="Dominio a reconfigurar"),
    v2: bool = typer.Option(False, "--v2", help="Usar bootstrap v2 (frontends, routes, upstreams declarativos)"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Sin prompts; falla si faltan datos"),
):
    """
    Reconfiguración completa de META (modo FULL).
    
    Solicita TODOS los campos META, incluyendo los ya existentes.
    Usa cuando quieras redefinir decisiones previas.
    
    Ejemplos:
        lsxtool servers reconfigure nginx dev-identity.lunarsystemx.com
    """
    console.print(Panel.fit(f"[bold cyan]Reconfiguración de {backend.upper()} - {domain}[/bold cyan]", border_style="cyan"))
    
    if backend == "nginx":
        if v2:
            _bootstrap_nginx_v2(domain, console, full_reconfigure=True, non_interactive=non_interactive)
        else:
            _bootstrap_nginx(domain, console, full_reconfigure=True)
    elif backend == "apache":
        console.print("[yellow]⚠️ Reconfigure de Apache aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")
    elif backend == "traefik":
        console.print("[yellow]⚠️ Reconfigure de Traefik aún no implementada[/yellow]")
        console.print("[dim]Esta funcionalidad será agregada próximamente[/dim]")


@app.command()
def apply(
    target: Optional[str] = typer.Argument(None, help="Dominio o archivo YAML (opcional, aplica todo si no se especifica)"),
    v2: bool = typer.Option(False, "--v2", help="Usar formato v2 (providers/.../sites/ + upstreams)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Aplicar sin confirmación (útil para CI/CD)")
):
    """
    Aplica estado declarativo (reconciliación).
    
    Regenera .conf desde YAML. Con --v2 usa providers/.../sites/ y upstreams v2.
    
    Ejemplos:
        lsxtool servers apply dev-identity.lunarsystemx.com --v2  # Regenera conf desde YAML v2
        lsxtool servers apply --v2                                # Aplica todos los sitios v2
        lsxtool servers apply --v2 --yes                          # Sin confirmación (CI/CD)
    """
    if v2:
        _apply_v2(target, yes, console)
        return

    import yaml
    from .declarative.state import StateEngine
    from .declarative.generator import ConfigGenerator
    from .declarative.loader import DeclarativeLoader
    from .declarative.models import DomainConfig
    from rich.prompt import Confirm

    console.print(Panel.fit("[bold cyan]Aplicar Estado Declarativo[/bold cyan]", border_style="cyan"))
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    loader = DeclarativeLoader(BASE_DIR, console)
    generator = ConfigGenerator(BASE_DIR, console)
    state_engine = StateEngine(BASE_DIR, console)
    
    # Cargar estado declarativo
    if not loader.load_all():
        console.print("[yellow]⚠️ No se encontró configuración declarativa[/yellow]")
        console.print("[dim]Ejecuta 'lsxtool servers bootstrap' primero[/dim]")
        return
    
    # Determinar qué aplicar
    if target:
        domain_config = None
        
        # Intentar como ruta de archivo (absoluta o relativa)
        yaml_path = None
        if target.endswith(".yaml") or target.endswith(".yml"):
            # Es un archivo YAML - intentar como ruta
            yaml_path = Path(target)
            if not yaml_path.is_absolute():
                # Relativo: intentar desde BASE_DIR o desde .lsxtool/
                if (BASE_DIR / target).exists():
                    yaml_path = BASE_DIR / target
                elif (BASE_DIR / ".lsxtool" / target).exists():
                    yaml_path = BASE_DIR / ".lsxtool" / target
                else:
                    # Intentar como ruta relativa desde .lsxtool/
                    declarative_root = BASE_DIR / ".lsxtool"
                    yaml_path = declarative_root / target if (declarative_root / target).exists() else None
            
            if yaml_path and yaml_path.exists():
                # Cargar directamente desde el archivo
                try:
                    with open(yaml_path, "r") as f:
                        data = yaml.safe_load(f) or {}
                    domain_config = DomainConfig(**data)
                    console.print(f"[cyan]✓[/cyan] Cargado desde: {yaml_path.relative_to(BASE_DIR)}")
                except Exception as e:
                    console.print(f"[red]❌ Error al cargar {yaml_path}: {e}[/red]")
                    return
        
        # Si no se cargó desde archivo, intentar como nombre de dominio
        if not domain_config:
            domain_name = Path(target).stem.replace(".yaml", "").replace(".yml", "") if target.endswith((".yaml", ".yml")) else target
            domain_config = loader.get_domain(domain_name)
        
        if not domain_config:
            console.print(f"[red]❌ No se encontró configuración para: {target}[/red]")
            console.print("[dim]💡 Verifica que el dominio exista en .lsxtool/providers/.../sites/ o .lsxtool/domains/[/dim]")
            return
        
        # Generar .conf
        console.print(f"\n[bold]Aplicando: {domain_config.domain}[/bold]")
        if generator.write_config(domain_config):
            console.print(f"[green]✅ Configuración aplicada[/green]")
        else:
            console.print(f"[red]❌ Error al aplicar configuración[/red]")
    else:
        # Aplicar todo
        console.print("\n[bold]Aplicando todas las configuraciones declarativas...[/bold]")
        
        if not loader._domains:
            console.print("[yellow]⚠️ No hay dominios configurados[/yellow]")
            return
        
        console.print(f"[cyan]Dominios encontrados: {len(loader._domains)}[/cyan]")
        
        if not yes:
            if not Confirm.ask("\n[bold yellow]¿Aplicar todas las configuraciones?[/bold yellow]", default=True):
                console.print("[yellow]Operación cancelada[/yellow]")
                return
        
        success_count = 0
        for domain_name, domain_config in loader._domains.items():
            console.print(f"\n[cyan]•[/cyan] {domain_name}")
            if generator.write_config(domain_config):
                success_count += 1
            else:
                console.print(f"  [red]❌ Error[/red]")
        
        console.print(f"\n[green]✅ Aplicadas: {success_count}/{len(loader._domains)}[/green]")


@app.command()
def drift(
    action: Literal["detect", "show"] = typer.Argument("detect", help="Acción: detect o show"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Dominio específico (opcional)")
):
    """
    Detecta drift entre estado deseado (YAML) y real (.conf).
    
    Ejemplos:
        lsxtool servers drift detect
        lsxtool servers drift detect --domain dev-identity.lunarsystemx.com
    """
    from .declarative.state import StateEngine
    
    console.print(Panel.fit("[bold cyan]Detección de Drift[/bold cyan]", border_style="cyan"))
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    state_engine = StateEngine(BASE_DIR, console)
    
    diffs = state_engine.detect_drift(domain)
    state_engine.display_drift(diffs)
    
    if diffs:
        console.print(f"\n[yellow]⚠️ Se detectaron {len(diffs)} diferencias[/yellow]")
        console.print("[dim]Ejecuta 'lsxtool servers apply' para reconciliar[/dim]")
    else:
        console.print("\n[green]✅ No hay drift. Estado sincronizado.[/green]")


@app.command()
def migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Solo muestra qué se migraría sin guardar")
):
    """
    Migra configuraciones legacy (.conf) a sistema declarativo (YAML).
    
    Convierte todos los .conf existentes con META a archivos YAML en .lsxtool/
    
    Ejemplos:
        lsxtool servers migrate              # Migra todo
        lsxtool servers migrate --dry-run    # Solo muestra qué se migraría
    """
    from .declarative.migrate import migrate_legacy
    
    console.print(Panel.fit("[bold cyan]Migración Legacy → Declarativo[/bold cyan]", border_style="cyan"))
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    migrated = migrate_legacy(BASE_DIR, console, dry_run=dry_run)
    
    if migrated > 0 and not dry_run:
        console.print(f"\n[green]✅ Migración completada: {migrated} dominios[/green]")
        console.print("[dim]Ejecuta 'lsxtool servers apply' para regenerar .conf desde YAML[/dim]")


@app.command()
def nginx(
    action: Literal["status", "reload", "restart", "test"] = typer.Argument("status", help="Acción a realizar")
):
    """
    Gestiona Nginx
    
    Ejemplos:
        lsxtool servers nginx status   # Ver estado
        lsxtool servers nginx reload    # Recargar configuración
        lsxtool servers nginx restart   # Reiniciar servicio
        lsxtool servers nginx test      # Validar configuración
    """
    console.print(Panel.fit(f"[bold cyan]Gestión de Nginx - {action.title()}[/bold cyan]", border_style="cyan"))
    
    if os.geteuid() != 0 and action != "status":
        console.print("[red]❌ Se requieren permisos de root para esta acción[/red]")
        console.print("[yellow]💡 Ejecuta con sudo preservando el entorno:[/yellow]")
        console.print(f"[cyan]   sudo -E python3 lsxtool/cli.py servers nginx {action}[/cyan]")
        console.print(f"[cyan]   o: sudo lsxtool/venv/bin/python3 lsxtool/cli.py servers nginx {action}[/cyan]")
        sys.exit(1)
    
    if action == "status":
        _nginx_status(console)
    elif action == "reload":
        _nginx_reload(console)
    elif action == "restart":
        _nginx_restart(console)
    elif action == "test":
        _nginx_test(console)


@app.command()
def apache(
    action: Literal["status", "reload", "restart", "test"] = typer.Argument("status", help="Acción a realizar")
):
    """
    Gestiona Apache
    
    Ejemplos:
        lsxtool servers apache status   # Ver estado
        lsxtool servers apache reload    # Recargar configuración
        lsxtool servers apache restart   # Reiniciar servicio
        lsxtool servers apache test      # Validar configuración
    """
    console.print(Panel.fit(f"[bold cyan]Gestión de Apache - {action.title()}[/bold cyan]", border_style="cyan"))
    
    if os.geteuid() != 0 and action != "status":
        console.print("[red]❌ Se requieren permisos de root para esta acción[/red]")
        console.print("[yellow]💡 Ejecuta con sudo preservando el entorno:[/yellow]")
        console.print(f"[cyan]   sudo -E python3 lsxtool/cli.py servers apache {action}[/cyan]")
        console.print(f"[cyan]   o: sudo lsxtool/venv/bin/python3 lsxtool/cli.py servers apache {action}[/cyan]")
        sys.exit(1)
    
    if action == "status":
        _apache_status(console)
    elif action == "reload":
        _apache_reload(console)
    elif action == "restart":
        _apache_restart(console)
    elif action == "test":
        _apache_test(console)


@app.command()
def traefik(
    action: Literal["status", "reload", "restart"] = typer.Argument("status", help="Acción a realizar")
):
    """
    Gestiona Traefik
    
    Ejemplos:
        lsxtool servers traefik status   # Ver estado
        lsxtool servers traefik reload    # Recargar configuración
        lsxtool servers traefik restart   # Reiniciar servicio
    """
    console.print(Panel.fit(f"[bold cyan]Gestión de Traefik - {action.title()}[/bold cyan]", border_style="cyan"))
    
    if os.geteuid() != 0 and action != "status":
        console.print("[red]❌ Se requieren permisos de root para esta acción[/red]")
        console.print("[yellow]💡 Ejecuta con sudo preservando el entorno:[/yellow]")
        console.print(f"[cyan]   sudo -E python3 lsxtool/cli.py servers traefik {action}[/cyan]")
        console.print(f"[cyan]   o: sudo lsxtool/venv/bin/python3 lsxtool/cli.py servers traefik {action}[/cyan]")
        sys.exit(1)
    
    if action == "status":
        _traefik_status(console)
    elif action == "reload":
        _traefik_reload(console)
    elif action == "restart":
        _traefik_restart(console)


def _nginx_status(console: Console):
    """Muestra estado de Nginx"""
    result = subprocess.run(
        ["systemctl", "status", "nginx", "--no-pager"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Nginx está activo[/green]")
        console.print("\n[dim]Detalles:[/dim]")
        console.print(result.stdout)
    else:
        console.print("[red]❌ Nginx no está activo o hay un error[/red]")
        if result.stderr:
            console.print(result.stderr)


def _nginx_reload(console: Console):
    """Recarga configuración de Nginx"""
    # Validar configuración primero
    test_result = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if test_result.returncode != 0:
        console.print("[red]❌ Error en configuración de Nginx[/red]")
        console.print(test_result.stderr)
        return
    
    result = subprocess.run(
        ["systemctl", "reload", "nginx"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Nginx recargado correctamente[/green]")
    else:
        console.print("[red]❌ Error al recargar Nginx[/red]")
        console.print(result.stderr)


def _nginx_restart(console: Console):
    """Reinicia Nginx"""
    result = subprocess.run(
        ["systemctl", "restart", "nginx"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Nginx reiniciado correctamente[/green]")
    else:
        console.print("[red]❌ Error al reiniciar Nginx[/red]")
        console.print(result.stderr)


def _nginx_test(console: Console):
    """Valida configuración de Nginx (sintaxis)"""
    result = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Configuración de Nginx válida[/green]")
        console.print(result.stdout)
    else:
        console.print("[red]❌ Error en configuración de Nginx[/red]")
        console.print(result.stderr)


def _verify_nginx(console: Console):
    """Verifica configuración Nginx con reglas avanzadas LSX"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.nginx.verify import verify_nginx_configs
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    success, results = verify_nginx_configs(BASE_DIR, console)
    
    # Exit code según resultado
    if not success:
        sys.exit(1)


def _inspect_nginx(domain: str, console: Console):
    """Inspecciona configuración Nginx de un dominio específico"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.nginx.inspect import inspect_nginx_domain
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    success = inspect_nginx_domain(domain, BASE_DIR, console)
    if not success:
        sys.exit(1)


def _fix_nginx(domain: str, console: Console):
    """Corrige problemas en configuración Nginx de un dominio"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.nginx.fix import fix_nginx_domain
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    success = fix_nginx_domain(domain, BASE_DIR, console)
    if not success:
        sys.exit(1)


def _bootstrap_nginx(domain: str, console: Console, full_reconfigure: bool = False):
    """Completa META (PATCH) o crea bloque META para un dominio Nginx. full_reconfigure=True solicita todos los campos."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.nginx.bootstrap import bootstrap_nginx_meta
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    success = bootstrap_nginx_meta(domain, BASE_DIR, console, full_reconfigure=full_reconfigure)
    if not success:
        sys.exit(1)


def _bootstrap_nginx_v2(domain: str, console: Console, full_reconfigure: bool = False, non_interactive: bool = False):
    """Bootstrap v2: frontends, routes, upstreams. full_reconfigure=True → reconfigure."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.nginx.bootstrap_v2 import bootstrap_nginx_v2
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    success = bootstrap_nginx_v2(domain, BASE_DIR, console, full_reconfigure=full_reconfigure, non_interactive=non_interactive)
    if not success:
        sys.exit(1)


def _apply_v2(target: Optional[str], yes: bool, console: Console):
    """Aplica estado v2: regenera .conf desde providers/.../sites/ + upstreams."""
    from pathlib import Path
    from rich.prompt import Confirm

    from .declarative.loader_v2 import load_domain
    from .declarative.generator_v2 import write_config_v2

    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    console.print(Panel.fit("[bold cyan]Aplicar Estado Declarativo (v2)[/bold cyan]", border_style="cyan"))

    def _list_v2_sites() -> list:
        """Lista dominios en providers/.../sites/*.yaml."""
        root = BASE_DIR / ".lsxtool" / "providers"
        if not root.exists():
            return []
        sites = []
        for pdir in root.iterdir():
            if not pdir.is_dir():
                continue
            nginx = pdir / "servers" / "nginx"
            if not nginx.exists():
                continue
            for edir in nginx.iterdir():
                if not edir.is_dir():
                    continue
                sdir = edir / "sites"
                if sdir.exists():
                    for f in sdir.glob("*.yaml"):
                        sites.append((f.stem, pdir.name, edir.name))
        return sites

    if target:
        domain = target.replace(".yaml", "").replace(".yml", "").strip()
        domain_config = load_domain(BASE_DIR, domain, console=console)
        if not domain_config:
            console.print(f"[red]❌ No se encontró configuración v2 para: {domain}[/red]")
            console.print("[dim]💡 Verifica que exista en .lsxtool/providers/<provider>/servers/nginx/<env>/sites/[/dim]")
            return
        provider_id = domain_config.provider or "lunarsystemx"
        env = domain_config.environment or "dev"
        console.print(f"\n[bold]Aplicando: {domain}[/bold]")
        if write_config_v2(BASE_DIR, domain_config, provider_id, env, console=console):
            console.print(f"[green]✅ Configuración aplicada[/green]")
        else:
            console.print(f"[red]❌ Error al aplicar configuración[/red]")
    else:
        sites = _list_v2_sites()
        if not sites:
            console.print("[yellow]⚠️ No hay sitios v2 en .lsxtool/providers/.../sites/[/yellow]")
            console.print("[dim]Ejecuta 'lsxtool servers bootstrap nginx <domain> --v2' primero[/dim]")
            return
        console.print(f"\n[bold]Sitios encontrados: {len(sites)}[/bold]")
        for dom, _, _ in sites:
            console.print(f"  [cyan]•[/cyan] {dom}")
        if not yes and not Confirm.ask("\n[bold yellow]¿Aplicar todas las configuraciones?[/bold yellow]", default=True):
            console.print("[yellow]Operación cancelada[/yellow]")
            return
        success = 0
        for domain, provider_id, env in sites:
            cfg = load_domain(BASE_DIR, domain, provider_id=provider_id, env=env, console=console)
            if cfg and write_config_v2(BASE_DIR, cfg, provider_id, env, console=console):
                success += 1
        console.print(f"\n[green]✅ Aplicadas: {success}/{len(sites)}[/green]")


def _apache_status(console: Console):
    """Muestra estado de Apache"""
    result = subprocess.run(
        ["systemctl", "status", "apache2", "--no-pager"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Apache está activo[/green]")
        console.print("\n[dim]Detalles:[/dim]")
        console.print(result.stdout)
    else:
        console.print("[red]❌ Apache no está activo o hay un error[/red]")
        if result.stderr:
            console.print(result.stderr)


def _apache_reload(console: Console):
    """Recarga configuración de Apache"""
    # Validar configuración primero
    test_result = subprocess.run(
        ["apache2ctl", "configtest"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if test_result.returncode != 0:
        console.print("[red]❌ Error en configuración de Apache[/red]")
        output = test_result.stdout + "\n" + test_result.stderr
        # Escapar rutas para Rich
        escaped_output = output.replace('[', '\\[').replace(']', '\\]')
        console.print(escaped_output)
        return
    
    result = subprocess.run(
        ["systemctl", "reload", "apache2"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Apache recargado correctamente[/green]")
    else:
        console.print("[red]❌ Error al recargar Apache[/red]")
        console.print(result.stderr)


def _apache_restart(console: Console):
    """Reinicia Apache"""
    result = subprocess.run(
        ["systemctl", "restart", "apache2"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Apache reiniciado correctamente[/green]")
    else:
        console.print("[red]❌ Error al reiniciar Apache[/red]")
        console.print(result.stderr)


def _apache_test(console: Console):
    """Valida configuración de Apache"""
    result = subprocess.run(
        ["apache2ctl", "configtest"],
        capture_output=True,
        text=True,
        check=False
    )
    
    output = result.stdout + "\n" + result.stderr
    escaped_output = output.replace('[', '\\[').replace(']', '\\]')
    
    if result.returncode == 0:
        console.print("[green]✅ Configuración de Apache válida[/green]")
        console.print(escaped_output)
    else:
        console.print("[red]❌ Error en configuración de Apache[/red]")
        console.print(escaped_output)


def _traefik_status(console: Console):
    """Muestra estado de Traefik"""
    result = subprocess.run(
        ["systemctl", "status", "traefik", "--no-pager"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Traefik está activo[/green]")
        console.print("\n[dim]Detalles:[/dim]")
        console.print(result.stdout)
    else:
        console.print("[red]❌ Traefik no está activo o hay un error[/red]")
        if result.stderr:
            console.print(result.stderr)


def _traefik_reload(console: Console):
    """Recarga configuración de Traefik"""
    result = subprocess.run(
        ["systemctl", "reload", "traefik"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Traefik recargado correctamente[/green]")
    else:
        # Intentar restart si reload no funciona
        restart_result = subprocess.run(
            ["systemctl", "restart", "traefik"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if restart_result.returncode == 0:
            console.print("[green]✅ Traefik reiniciado correctamente[/green]")
        else:
            console.print("[red]❌ Error al recargar/reiniciar Traefik[/red]")
            console.print(restart_result.stderr)


def _traefik_restart(console: Console):
    """Reinicia Traefik"""
    result = subprocess.run(
        ["systemctl", "restart", "traefik"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if result.returncode == 0:
        console.print("[green]✅ Traefik reiniciado correctamente[/green]")
    else:
        console.print("[red]❌ Error al reiniciar Traefik[/red]")
        console.print(result.stderr)


@app.command()
def sync(
    service: Optional[Literal["traefik", "apache", "nginx", "all"]] = typer.Argument(
        None, help="Servicio a sincronizar (traefik, apache, nginx, all)"
    )
):
    """
    Sincroniza cambios de configuración de Traefik, Apache o Nginx
    
    Ejemplos:
        lsxtool servers sync              # Sincronización interactiva
        lsxtool servers sync traefik      # Sincronizar solo Traefik
        lsxtool servers sync apache       # Sincronizar solo Apache
        lsxtool servers sync nginx        # Sincronizar solo Nginx
        lsxtool servers sync all          # Sincronizar todos
    """
    sync_configs(service, SERVERS_DIR, console)


@app.command()
def add():
    """
    Wizard interactivo para crear configuración de servidor.
    
    Genera un archivo YAML en ~/.lsxtool/{provider}/servers/{service}/{env}/{target}-{name}.yml
    que define las rutas de sincronización y comandos de validación/recarga.
    
    Ejemplo:
        lsxtool servers add
    """
    try:
        # Recopilar datos del wizard
        wizard_data = collect_wizard_data(BASE_DIR, console)

        # Modo import: crear workspace y detectar rutas (muestra en terminal)
        if wizard_data.get("mode") == "import":
            wizard_data["import_routes"] = run_import_discovery_and_create_workspace(wizard_data, console)

        # Generar estructura YAML
        yaml_config = generate_yaml_config(wizard_data)
        
        # Obtener ruta del archivo
        config_path = get_config_path(
            wizard_data["provider"],
            wizard_data["service"],
            wizard_data["environment"],
            wizard_data["server_name"],
        )
        
        # Verificar si el archivo ya existe
        if config_path.exists():
            from rich.prompt import Confirm
            if not Confirm.ask(f"\n[yellow]⚠ El archivo ya existe: {config_path}[/yellow]\n¿Sobrescribir?", default=False):
                console.print("[yellow]Operación cancelada[/yellow]")
                return
        
        # Escribir archivo
        written_path = write_config_file(yaml_config, config_path, console)
        
        # Mostrar éxito
        console.print(f"\n[green]✓ Servidor {wizard_data['service']}/{wizard_data['environment']} creado[/green]")
        console.print(f"  [dim]{written_path}[/dim]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operación cancelada por el usuario[/yellow]")
    except MissingCapabilityError:
        # Mensaje ya mostrado por ensure_servers_web_capability
        raise SystemExit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


@app.command()
def sites(
    action: Literal["create", "list", "status", "info", "meta"] = typer.Argument("list", help="Acción a realizar"),
    domain: Optional[str] = typer.Argument(None, help="Dominio (requerido para 'info' y 'meta')"),
    full: bool = typer.Option(False, "--full", "-f", help="Vista completa con todos los detalles")
):
    """
    Gestiona sitios web configurados
    
    Ejemplos:
        lsxtool servers sites list                    # Vista resumida
        lsxtool servers sites list --full             # Vista completa
        lsxtool servers sites info <domain>           # Información detallada de un sitio
        lsxtool servers sites meta <domain>           # Configurar/actualizar metadatos
        lsxtool servers sites create                  # Crear un nuevo sitio
        lsxtool servers sites status                  # Ver estado de sitios
    """
    if action == "create":
        create_site(None, None, SERVERS_DIR, console)
    elif action == "list":
        _list_sites(console, full=full)
    elif action == "status":
        _sites_status(console)
    elif action == "info":
        if not domain:
            console.print("[red]❌ Se requiere especificar un dominio[/red]")
            console.print("[yellow]Uso: lsxtool servers sites info <domain>[/yellow]")
            raise typer.Exit(code=1)
        _show_site_info(domain, console)
    elif action == "meta":
        if not domain:
            console.print("[red]❌ Se requiere especificar un dominio[/red]")
            console.print("[yellow]Uso: lsxtool servers sites meta <domain>[/yellow]")
            raise typer.Exit(code=1)
        # Usar la última definición de _manage_site_meta
        _manage_site_meta(domain, console)


def _list_sites(console: Console, full: bool = False):
    """Lista todos los sitios configurados con vista operativa"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import load_all_sites
    from servers.sites.server_version import get_server_version_display
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    
    console.print(Panel.fit("[bold cyan]Sitios Configurados[/bold cyan]", border_style="cyan"))
    
    # Obtener directorio base (servers-install/)
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    # Cargar todos los sitios
    sites = load_all_sites(BASE_DIR, console)
    
    if not sites:
        console.print("[yellow]⚠️ No se encontraron sitios configurados[/yellow]")
        return
    
    # Ordenar por proveedor, backend, ambiente, y luego dominio
    sorted_sites = sorted(
        sites,
        key=lambda x: (
            x.provider,
            x.backend_type.lower(),
            x.environment.lower(),
            x.domain
        )
    )
    
    # Estadísticas por proveedor (antes de filtrar)
    providers_count = {}
    for site in sites:
        provider = site.provider
        providers_count[provider] = providers_count.get(provider, 0) + 1
    
    # Filtro por proveedor ANTES de hacer health checks
    filtered_sites = sorted_sites
    selected_provider = None
    
    if len(providers_count) > 1:
        providers_list = sorted(providers_count.keys())
        console.print("\n[bold cyan]Proveedores disponibles:[/bold cyan]")
        for idx, provider in enumerate(providers_list, 1):
            count = providers_count[provider]
            console.print(f"  [cyan]{idx}.[/cyan] {provider} [dim]({count} sitio{'s' if count != 1 else ''})[/dim]")
        console.print(f"  [cyan]0.[/cyan] Todos [dim]({len(sites)} sitios)[/dim]")
        
        try:
            choice = Prompt.ask(
                "\n[bold]Selecciona un proveedor[/bold]",
                choices=[str(i) for i in range(0, len(providers_list) + 1)],
                default="0"
            )
            
            if choice != "0":
                selected_provider = providers_list[int(choice) - 1]
                filtered_sites = [s for s in sorted_sites if s.provider == selected_provider]
                console.print(f"\n[bold cyan]Filtrando por: {selected_provider}[/bold cyan]")
            else:
                console.print("\n[bold cyan]Mostrando todos los proveedores[/bold cyan]")
        except (ValueError, KeyboardInterrupt):
            console.print("\n[yellow]Operación cancelada[/yellow]")
            return
    
    if full:
        # Vista completa enterprise
        from servers.sites.health_check import check_site_health, format_health_status
        
        table = Table(title="Sitios - Vista Completa", show_header=True, header_style="bold cyan")
        table.add_column("Dominio", style="cyan", width=35)
        table.add_column("Proveedor", style="yellow", width=10)
        table.add_column("Ambiente", style="green", width=8)
        table.add_column("Tipo", style="blue", width=8)
        table.add_column("Server Web", style="magenta", width=18)
        table.add_column("Tech", style="dim", width=12)
        table.add_column("Health", style="green", width=30)
        table.add_column("Dueño", style="yellow", width=20)
        
        console.print("[dim]Verificando estado de sitios...[/dim]")
        
        for site in filtered_sites:
            # Obtener versión del servidor web
            server_version = get_server_version_display(site.backend_type)
            
            # Realizar health check para todos los sitios (incluyendo dashboard)
            health_result = check_site_health(site.domain, timeout=3)
            
            # Si es servicio interno de Traefik, mostrar estado especial
            if site.backend_type and site.backend_type.upper() == "TRAEFIK":
                http_code = health_result.get("http_code")
                response_ip = health_result.get("response_ip")
                
                # Formatear IP si existe (igual que en format_health_status)
                ip_suffix = ""
                if response_ip:
                    if response_ip not in ["127.0.0.1", "localhost", "::1"]:
                        ip_suffix = f" ({response_ip})"
                    else:
                        ip_suffix = " (localhost)"
                
                if http_code in [200, 401, 403]:
                    # Si responde con 200, 401 o 403, el servicio está vivo y protegido
                    health_status = f"[green]✅[/green] [dim]🔒 INTERNAL[/dim] {http_code}{ip_suffix}"
                elif http_code:
                    # Cualquier otro código HTTP también indica que está vivo
                    health_status = f"[yellow]⚠[/yellow] [dim]🔒 INTERNAL[/dim] {http_code}{ip_suffix}"
                else:
                    health_status = f"[red]❌[/red] [dim]🔒 INTERNAL[/dim] DOWN{ip_suffix}"
            else:
                # Formatear health check normal
                health_status = format_health_status(health_result)
            
            # Obtener tech_version del manifest
            tech_display = "N/A"
            if site.manifest and site.manifest.tech_version:
                tech_display = site.manifest.tech_version
            elif site.manifest and site.manifest.tech:
                # Si solo hay tech sin versión, mostrar tech
                tech_display = site.manifest.tech.upper()
            
            table.add_row(
                site.domain,
                site.provider,
                site.environment.upper(),
                site.service_type.upper(),
                server_version,
                tech_display,
                health_status,
                site.owner or "N/A"
            )
    else:
        # Vista resumida operativa
        from servers.sites.health_check import check_site_health, format_health_status
        
        table = Table(title="Sitios - Vista Operativa", show_header=True, header_style="bold cyan")
        table.add_column("Dominio", style="cyan", width=35)
        if selected_provider is None:
            table.add_column("Proveedor", style="yellow", width=10)
        table.add_column("Ambiente", style="green", width=8)
        table.add_column("Server Web", style="magenta", width=18)
        table.add_column("Tech", style="dim", width=12)
        table.add_column("Health", style="green", width=30)
        table.add_column("Dueño", style="yellow", width=20)
        
        console.print("[dim]Verificando estado de sitios...[/dim]")
        
        for site in filtered_sites:
            # Obtener versión del servidor web
            server_version = get_server_version_display(site.backend_type)
            
            # Realizar health check para todos los sitios (incluyendo dashboard)
            health_result = check_site_health(site.domain, timeout=3)
            
            # Si es servicio interno de Traefik, mostrar estado especial
            if site.backend_type and site.backend_type.upper() == "TRAEFIK":
                http_code = health_result.get("http_code")
                response_ip = health_result.get("response_ip")
                
                # Formatear IP si existe (igual que en format_health_status)
                ip_suffix = ""
                if response_ip:
                    if response_ip not in ["127.0.0.1", "localhost", "::1"]:
                        ip_suffix = f" ({response_ip})"
                    else:
                        ip_suffix = " (localhost)"
                
                if http_code in [200, 401, 403]:
                    # Si responde con 200, 401 o 403, el servicio está vivo y protegido
                    health_status = f"[green]✅[/green] [dim]🔒 INTERNAL[/dim] {http_code}{ip_suffix}"
                elif http_code:
                    # Cualquier otro código HTTP también indica que está vivo
                    health_status = f"[yellow]⚠[/yellow] [dim]🔒 INTERNAL[/dim] {http_code}{ip_suffix}"
                else:
                    health_status = f"[red]❌[/red] [dim]🔒 INTERNAL[/dim] DOWN{ip_suffix}"
            else:
                # Formatear health check normal
                health_status = format_health_status(health_result)
            
            # Obtener tech_version del manifest
            tech_display = "N/A"
            if site.manifest and site.manifest.tech_version:
                tech_display = site.manifest.tech_version
            elif site.manifest and site.manifest.tech:
                # Si solo hay tech sin versión, mostrar tech
                tech_display = site.manifest.tech.upper()
            
            row_data = [
                site.domain,
                site.environment.upper(),
                server_version,
                tech_display,
                health_status,
                site.owner or "N/A"
            ]
            
            # Agregar proveedor solo si no está filtrado
            if selected_provider is None:
                row_data.insert(1, site.provider)
            
            table.add_row(*row_data)
    
    console.print(table)
    
    # Mostrar estadísticas
    if selected_provider:
        console.print(f"\n[bold cyan]Total {selected_provider}:[/bold cyan] [green]{len(filtered_sites)} sitio(s)[/green]")
    else:
        console.print(f"\n[dim]Total: {len(filtered_sites)} sitio(s)[/dim]")
        if len(providers_count) > 1:
            providers_summary = ", ".join([f"{k}: {v}" for k, v in sorted(providers_count.items())])
            console.print(f"[dim]Por proveedor: {providers_summary}[/dim]")
    
    if not full:
        console.print("[dim]Usa --full para ver todos los detalles[/dim]")
    
    console.print()


def _manage_site_meta(domain: str, console: Console):
    """Gestiona metadatos de un sitio (configurar/actualizar)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import get_site_info
    from servers.sites.meta_parser import parse_meta_from_conf, write_meta_to_conf, validate_meta
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    # Obtener información del sitio
    site_info = get_site_info(domain, BASE_DIR, console)
    
    if not site_info:
        console.print(f"[red]❌ Sitio '{domain}' no encontrado[/red]")
        console.print("[yellow]Usa 'lsxtool servers sites list' para ver sitios disponibles[/yellow]")
        return
    
    # Buscar archivo de configuración
    config_path = None
    if site_info.config_path and site_info.config_path != "N/A":
        config_path = Path(site_info.config_path)
        if not config_path.is_absolute():
            config_path = BASE_DIR / config_path
    else:
        # Buscar archivo de configuración
        apache_paths = [
            BASE_DIR / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
            BASE_DIR / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
        ]
        
        nginx_paths = [
            BASE_DIR / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            BASE_DIR / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
        ]
        
        for path in apache_paths + nginx_paths:
            if path.exists():
                config_path = path
                break
    
    if not config_path or not config_path.exists():
        console.print(f"[red]❌ No se encontró archivo de configuración para {domain}[/red]")
        return
    
    console.print(Panel.fit(f"[bold cyan]Gestión de Metadatos - {domain}[/bold cyan]", border_style="cyan"))
    
    # Leer metadatos actuales
    current_meta = parse_meta_from_conf(config_path)
    
    if current_meta:
        console.print("\n[bold]Metadatos actuales:[/bold]")
        meta_table = Table(show_header=False, box=None)
        meta_table.add_column("Campo", style="cyan", width=20)
        meta_table.add_column("Valor", style="green")
        
        for key, value in sorted(current_meta.items()):
            meta_table.add_row(key, value)
        
        console.print(meta_table)
    else:
        console.print("\n[yellow]⚠️ No hay metadatos configurados actualmente[/yellow]")
        current_meta = {}
    
    # Preguntar si actualizar
    if not Confirm.ask("\n¿Deseas actualizar los metadatos?", default=True):
        return
    
    # Importar catálogos
    from servers.sites.catalogs import (
        get_owners,
        get_providers,
        get_service_types,
        get_environments,
        get_backends,
        get_backend_versions
    )
    
    # Recopilar nuevos valores desde catálogos controlados
    console.print("\n[bold]Ingresa los metadatos desde catálogos controlados:[/bold]")
    
    # Owner desde catálogo
    owners_list = get_owners()
    console.print("\n[bold cyan]Equipos disponibles:[/bold cyan]")
    for idx, owner_item in enumerate(owners_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {owner_item}")
    
    owner_choice = Prompt.ask(
        "\n[bold]Selecciona Owner/Equipo responsable[/bold]",
        choices=[str(i) for i in range(1, len(owners_list) + 1)],
        default=str(1) if owners_list else None
    )
    owner = owners_list[int(owner_choice) - 1] if owner_choice else ""
    
    # Proveedor desde catálogo
    providers_list = get_providers()
    current_provider_idx = 0
    if current_meta.get("provider") in providers_list:
        current_provider_idx = providers_list.index(current_meta.get("provider")) + 1
    
    console.print("\n[bold cyan]Proveedores disponibles:[/bold cyan]")
    for idx, provider_item in enumerate(providers_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {provider_item}")
    
    provider_choice = Prompt.ask(
        "\n[bold]Selecciona Proveedor[/bold]",
        choices=[str(i) for i in range(1, len(providers_list) + 1)],
        default=str(current_provider_idx) if current_provider_idx > 0 else "1"
    )
    provider = providers_list[int(provider_choice) - 1]
    
    # Tipo de servicio desde catálogo
    service_types_list = get_service_types()
    current_service_type_idx = 0
    if current_meta.get("service_type") in service_types_list:
        current_service_type_idx = service_types_list.index(current_meta.get("service_type")) + 1
    
    console.print("\n[bold cyan]Tipos de servicio disponibles:[/bold cyan]")
    for idx, st_item in enumerate(service_types_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {st_item}")
    
    service_type_choice = Prompt.ask(
        "\n[bold]Selecciona Tipo de servicio[/bold]",
        choices=[str(i) for i in range(1, len(service_types_list) + 1)],
        default=str(current_service_type_idx) if current_service_type_idx > 0 else "1"
    )
    service_type = service_types_list[int(service_type_choice) - 1]
    
    # Ambiente desde catálogo
    environments_list = get_environments()
    current_env_idx = 0
    if current_meta.get("environment") in environments_list:
        current_env_idx = environments_list.index(current_meta.get("environment")) + 1
    
    console.print("\n[bold cyan]Ambientes disponibles:[/bold cyan]")
    for idx, env_item in enumerate(environments_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {env_item}")
    
    environment_choice = Prompt.ask(
        "\n[bold]Selecciona Ambiente[/bold]",
        choices=[str(i) for i in range(1, len(environments_list) + 1)],
        default=str(current_env_idx) if current_env_idx > 0 else "1"
    )
    environment = environments_list[int(environment_choice) - 1]
    
    # Backend desde catálogo
    backends_list = get_backends()
    current_backend = current_meta.get("backend", site_info.backend_type.lower())
    current_backend_idx = 0
    if current_backend in backends_list:
        current_backend_idx = backends_list.index(current_backend) + 1
    
    console.print("\n[bold cyan]Backends disponibles:[/bold cyan]")
    for idx, backend_item in enumerate(backends_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {backend_item}")
    
    backend_choice = Prompt.ask(
        "\n[bold]Selecciona Backend[/bold]",
        choices=[str(i) for i in range(1, len(backends_list) + 1)],
        default=str(current_backend_idx) if current_backend_idx > 0 else "1"
    )
    backend = backends_list[int(backend_choice) - 1]
    
    # Versión del backend - solo mostrar versiones disponibles
    backend_versions = get_backend_versions(backend)
    
    if backend_versions:
        console.print(f"\n[bold cyan]Versiones disponibles de {backend.upper()}:[/bold cyan]")
        for idx, version_item in enumerate(backend_versions, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {version_item}")
        
        current_version_idx = 0
        if current_meta.get("backend_version") in backend_versions:
            current_version_idx = backend_versions.index(current_meta.get("backend_version")) + 1
        
        version_choice = Prompt.ask(
            f"\n[bold]Selecciona Versión de {backend.upper()}[/bold]",
            choices=[str(i) for i in range(1, len(backend_versions) + 1)],
            default=str(current_version_idx) if current_version_idx > 0 else "1"
        )
        backend_version = backend_versions[int(version_choice) - 1]
    else:
        console.print(f"\n[yellow]⚠️ No se detectó versión de {backend.upper()} instalada[/yellow]")
        backend_version = Prompt.ask(
            f"Versión de {backend.upper()} (manual)",
            default=current_meta.get("backend_version", "")
        )
    
    # Construir dict de metadatos
    new_meta = {
        "owner": owner,
        "provider": provider,
        "service_type": service_type,
        "environment": environment,
        "backend": backend,
        "backend_version": backend_version
    }
    
    # Validar
    is_valid, warnings = validate_meta(new_meta, console)
    
    if warnings and not Confirm.ask("\n¿Continuar a pesar de las advertencias?", default=True):
        return
    
    # Escribir metadatos
    if write_meta_to_conf(config_path, new_meta, console):
        console.print(f"\n[bold green]✅ Metadatos actualizados para {domain}[/bold green]")
        console.print(f"[dim]Archivo: {config_path}[/dim]")
        
        # Mostrar resumen
        console.print("\n[bold]Metadatos actualizados:[/bold]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Campo", style="cyan", width=20)
        summary_table.add_column("Valor", style="green")
        
        for key, value in sorted(new_meta.items()):
            summary_table.add_row(key, value)
        
        console.print(summary_table)
        
        console.print(f"\n[yellow]💡 Ejecuta 'lsxtool servers sites info {domain}' para ver los cambios[/yellow]")
    else:
        console.print(f"\n[red]❌ Error al actualizar metadatos[/red]")
    
    console.print()


def _sites_status(console: Console):
    """Muestra el estado operativo de los sitios configurados"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import load_all_sites
    
    console.print(Panel.fit("[bold cyan]Estado de Sitios[/bold cyan]", border_style="cyan"))
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    sites = load_all_sites(BASE_DIR, console)
    
    if not sites:
        console.print("[yellow]⚠️ No se encontraron sitios configurados[/yellow]")
        return
    
    table = Table(title="Estado Operativo de Sitios", show_header=True, header_style="bold cyan")
    table.add_column("Dominio", style="cyan", width=35)
    table.add_column("Backend", style="yellow", width=12)
    table.add_column("Estado Traefik", style="green", width=15)
    table.add_column("Estado Backend", style="green", width=15)
    table.add_column("Target", style="dim", width=15)
    
    # Verificar estado de servicios
    traefik_active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "traefik"],
        check=False
    ).returncode == 0
    
    apache_active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "apache2"],
        check=False
    ).returncode == 0
    
    nginx_active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "nginx"],
        check=False
    ).returncode == 0
    
    for site in sorted(sites, key=lambda x: x.domain):
        traefik_status = "[green]✅ Activo[/green]" if traefik_active else "[red]❌ Inactivo[/red]"
        
        # Verificar estado del backend según tipo
        backend_status = "[dim]N/A[/dim]"
        if site.backend_type.lower() == "apache":
            backend_status = "[green]✅ Activo[/green]" if apache_active else "[red]❌ Inactivo[/red]"
        elif site.backend_type.lower() == "nginx":
            backend_status = "[green]✅ Activo[/green]" if nginx_active else "[red]❌ Inactivo[/red]"
        
        table.add_row(
            site.domain,
            site.backend_type.upper(),
            traefik_status,
            backend_status,
            site.target
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(sites)} sitio(s)[/dim]")
    console.print()


def _manage_site_meta(domain: str, console: Console):
    """Gestiona metadatos de un sitio (configurar/actualizar)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import get_site_info
    from servers.sites.meta_parser import parse_meta_from_conf, write_meta_to_conf, validate_meta
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    # Obtener información del sitio
    site_info = get_site_info(domain, BASE_DIR, console)
    
    if not site_info:
        console.print(f"[red]❌ Sitio '{domain}' no encontrado[/red]")
        console.print("[yellow]Usa 'lsxtool servers sites list' para ver sitios disponibles[/yellow]")
        return
    
    # Buscar archivo de configuración
    config_path = None
    if site_info.config_path and site_info.config_path != "N/A":
        config_path = Path(site_info.config_path)
        if not config_path.is_absolute():
            config_path = BASE_DIR / config_path
    else:
        # Buscar archivo de configuración
        apache_paths = [
            BASE_DIR / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
            BASE_DIR / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
        ]
        
        nginx_paths = [
            BASE_DIR / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            BASE_DIR / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
        ]
        
        for path in apache_paths + nginx_paths:
            if path.exists():
                config_path = path
                break
    
    if not config_path or not config_path.exists():
        console.print(f"[red]❌ No se encontró archivo de configuración para {domain}[/red]")
        return
    
    console.print(Panel.fit(f"[bold cyan]Gestión de Metadatos - {domain}[/bold cyan]", border_style="cyan"))
    
    # Leer metadatos actuales
    current_meta = parse_meta_from_conf(config_path)
    
    if current_meta:
        console.print("\n[bold]Metadatos actuales:[/bold]")
        meta_table = Table(show_header=False, box=None)
        meta_table.add_column("Campo", style="cyan", width=20)
        meta_table.add_column("Valor", style="green")
        
        for key, value in sorted(current_meta.items()):
            meta_table.add_row(key, value)
        
        console.print(meta_table)
    else:
        console.print("\n[yellow]⚠️ No hay metadatos configurados actualmente[/yellow]")
        current_meta = {}
    
    # Preguntar si actualizar
    if not Confirm.ask("\n¿Deseas actualizar los metadatos?", default=True):
        return
    
    # Importar catálogos
    from servers.sites.catalogs import (
        get_owners,
        get_providers,
        get_service_types,
        get_environments,
        get_backends,
        get_backend_versions
    )
    
    # Recopilar nuevos valores desde catálogos controlados
    console.print("\n[bold]Ingresa los metadatos desde catálogos controlados:[/bold]")
    
    # Owner desde catálogo
    owners_list = get_owners()
    console.print("\n[bold cyan]Equipos disponibles:[/bold cyan]")
    for idx, owner_item in enumerate(owners_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {owner_item}")
    
    owner_choice = Prompt.ask(
        "\n[bold]Selecciona Owner/Equipo responsable[/bold]",
        choices=[str(i) for i in range(1, len(owners_list) + 1)],
        default=str(1) if owners_list else None
    )
    owner = owners_list[int(owner_choice) - 1] if owner_choice else ""
    
    # Proveedor desde catálogo
    providers_list = get_providers()
    current_provider_idx = 0
    if current_meta.get("provider") in providers_list:
        current_provider_idx = providers_list.index(current_meta.get("provider")) + 1
    
    console.print("\n[bold cyan]Proveedores disponibles:[/bold cyan]")
    for idx, provider_item in enumerate(providers_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {provider_item}")
    
    provider_choice = Prompt.ask(
        "\n[bold]Selecciona Proveedor[/bold]",
        choices=[str(i) for i in range(1, len(providers_list) + 1)],
        default=str(current_provider_idx) if current_provider_idx > 0 else "1"
    )
    provider = providers_list[int(provider_choice) - 1]
    
    # Tipo de servicio desde catálogo
    service_types_list = get_service_types()
    current_service_type_idx = 0
    if current_meta.get("service_type") in service_types_list:
        current_service_type_idx = service_types_list.index(current_meta.get("service_type")) + 1
    
    console.print("\n[bold cyan]Tipos de servicio disponibles:[/bold cyan]")
    for idx, st_item in enumerate(service_types_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {st_item}")
    
    service_type_choice = Prompt.ask(
        "\n[bold]Selecciona Tipo de servicio[/bold]",
        choices=[str(i) for i in range(1, len(service_types_list) + 1)],
        default=str(current_service_type_idx) if current_service_type_idx > 0 else "1"
    )
    service_type = service_types_list[int(service_type_choice) - 1]
    
    # Ambiente desde catálogo
    environments_list = get_environments()
    current_env_idx = 0
    if current_meta.get("environment") in environments_list:
        current_env_idx = environments_list.index(current_meta.get("environment")) + 1
    
    console.print("\n[bold cyan]Ambientes disponibles:[/bold cyan]")
    for idx, env_item in enumerate(environments_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {env_item}")
    
    environment_choice = Prompt.ask(
        "\n[bold]Selecciona Ambiente[/bold]",
        choices=[str(i) for i in range(1, len(environments_list) + 1)],
        default=str(current_env_idx) if current_env_idx > 0 else "1"
    )
    environment = environments_list[int(environment_choice) - 1]
    
    # Backend desde catálogo
    backends_list = get_backends()
    current_backend = current_meta.get("backend", site_info.backend_type.lower())
    current_backend_idx = 0
    if current_backend in backends_list:
        current_backend_idx = backends_list.index(current_backend) + 1
    
    console.print("\n[bold cyan]Backends disponibles:[/bold cyan]")
    for idx, backend_item in enumerate(backends_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {backend_item}")
    
    backend_choice = Prompt.ask(
        "\n[bold]Selecciona Backend[/bold]",
        choices=[str(i) for i in range(1, len(backends_list) + 1)],
        default=str(current_backend_idx) if current_backend_idx > 0 else "1"
    )
    backend = backends_list[int(backend_choice) - 1]
    
    # Versión del backend - solo mostrar versiones disponibles
    backend_versions = get_backend_versions(backend)
    
    if backend_versions:
        console.print(f"\n[bold cyan]Versiones disponibles de {backend.upper()}:[/bold cyan]")
        for idx, version_item in enumerate(backend_versions, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {version_item}")
        
        current_version_idx = 0
        if current_meta.get("backend_version") in backend_versions:
            current_version_idx = backend_versions.index(current_meta.get("backend_version")) + 1
        
        version_choice = Prompt.ask(
            f"\n[bold]Selecciona Versión de {backend.upper()}[/bold]",
            choices=[str(i) for i in range(1, len(backend_versions) + 1)],
            default=str(current_version_idx) if current_version_idx > 0 else "1"
        )
        backend_version = backend_versions[int(version_choice) - 1]
    else:
        console.print(f"\n[yellow]⚠️ No se detectó versión de {backend.upper()} instalada[/yellow]")
        backend_version = Prompt.ask(
            f"Versión de {backend.upper()} (manual)",
            default=current_meta.get("backend_version", "")
        )
    
    # Construir dict de metadatos
    new_meta = {
        "owner": owner,
        "provider": provider,
        "service_type": service_type,
        "environment": environment,
        "backend": backend,
        "backend_version": backend_version
    }
    
    # Validar
    is_valid, warnings = validate_meta(new_meta, console)
    
    if warnings and not Confirm.ask("\n¿Continuar a pesar de las advertencias?", default=True):
        return
    
    # Escribir metadatos
    if write_meta_to_conf(config_path, new_meta, console):
        console.print(f"\n[bold green]✅ Metadatos actualizados para {domain}[/bold green]")
        console.print(f"[dim]Archivo: {config_path}[/dim]")
        
        # Mostrar resumen
        console.print("\n[bold]Metadatos actualizados:[/bold]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Campo", style="cyan", width=20)
        summary_table.add_column("Valor", style="green")
        
        for key, value in sorted(new_meta.items()):
            summary_table.add_row(key, value)
        
        console.print(summary_table)
        
        console.print(f"\n[yellow]💡 Ejecuta 'lsxtool servers sites info {domain}' para ver los cambios[/yellow]")
    else:
        console.print(f"\n[red]❌ Error al actualizar metadatos[/red]")
    
    console.print()


def _show_site_info(domain: str, console: Console):
    """Muestra información detallada de un sitio (ficha técnica)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import get_site_info
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    site_info = get_site_info(domain, BASE_DIR, console)
    
    if not site_info:
        console.print(f"[red]❌ Sitio '{domain}' no encontrado[/red]")
        console.print("[yellow]Usa 'lsxtool servers sites list' para ver sitios disponibles[/yellow]")
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
    tech_table.add_column("Valor", style="green", overflow="fold")
    
    tech_table.add_row("Backend Type", site_info.backend_type.upper())
    tech_table.add_row("Backend Version", site_info.backend_version if site_info.backend_version and site_info.backend_version != "N/A" else "N/A")
    tech_table.add_row("Tech Version", site_info.tech_version if site_info.tech_version != "N/A" else "N/A")
    tech_table.add_row("Target", site_info.target)
    tech_table.add_row("Ruta en Servidor", site_info.path)
    
    # Mostrar archivo .conf (no Traefik)
    config_path_created = None
    if site_info.config_path and site_info.config_path != "N/A":
        # Mostrar ruta relativa si es posible
        config_path_display = site_info.config_path
        try:
            config_path_obj = Path(site_info.config_path)
            if not config_path_obj.is_absolute():
                config_path_obj = BASE_DIR / config_path_obj
            
            if config_path_obj.exists():
                # Intentar mostrar ruta relativa desde servers-install
                try:
                    rel_path = config_path_obj.relative_to(BASE_DIR)
                    config_path_display = str(rel_path)
                except:
                    config_path_display = str(config_path_obj)
        except:
            pass
        tech_table.add_row("Archivo Config", config_path_display)
    else:
        tech_table.add_row("Archivo Config", "[yellow]No encontrado[/yellow]")
        
        # Ofrecer crear el archivo .conf (solo una vez)
        from servers.sites.conf_creator import create_conf_file, update_hosts_file
        from rich.prompt import Confirm
        
        if Confirm.ask("\n¿Deseas crear el archivo .conf ahora?", default=True):
            config_path_created = create_conf_file(
                domain,
                site_info.backend_type.lower() if site_info.backend_type else None,
                BASE_DIR,
                console,
                site_info.target
            )
            
            if config_path_created:
                # Preguntar si modificar hosts (solo si tiene permisos)
                import os
                if os.geteuid() == 0:
                    # Tenemos permisos de root
                    if Confirm.ask("\n¿Deseas agregar este dominio a /etc/hosts (apuntar a localhost)?", default=True):
                        update_hosts_file(domain, console)
                else:
                    # No tenemos permisos, solo informar
                    if Confirm.ask("\n¿Deseas agregar este dominio a /etc/hosts (apuntar a localhost)?", default=False):
                        update_hosts_file(domain, console)  # Mostrará instrucciones manuales
                
                console.print("\n[yellow]💡 Recarga la configuración del servidor web para aplicar los cambios[/yellow]")
                if site_info.backend_type:
                    console.print(f"[cyan]   Ejecuta: sudo lsxtool servers {site_info.backend_type.lower()} reload[/cyan]")
    
    if site_info.manifest and site_info.manifest.tags:
        tech_table.add_row("Tags", ", ".join(site_info.manifest.tags))
    
    console.print(tech_table)
    
    # Información de Traefik (referencia secundaria)
    if site_info.traefik_data:
        console.print("\n[bold]Configuración Traefik[/bold] [dim](Referencia)[/dim]")
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
        
        # Mostrar archivo de Traefik aquí, no en Información Técnica
        if hasattr(site_info, '_traefik_file_path') and site_info._traefik_file_path != "N/A":
            traefik_path_display = site_info._traefik_file_path
            try:
                traefik_path_obj = Path(site_info._traefik_file_path)
                if not traefik_path_obj.is_absolute():
                    traefik_path_obj = BASE_DIR / traefik_path_obj
                
                if traefik_path_obj.exists():
                    try:
                        rel_path = traefik_path_obj.relative_to(BASE_DIR)
                        traefik_path_display = str(rel_path)
                    except:
                        traefik_path_display = str(traefik_path_obj)
            except:
                pass
            traefik_table.add_row("Archivo Config", traefik_path_display)
        
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


def _manage_site_meta(domain: str, console: Console):
    """Gestiona metadatos de un sitio (configurar/actualizar)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from servers.sites.sites_manager import get_site_info
    from servers.sites.meta_parser import parse_meta_from_conf, write_meta_to_conf, validate_meta
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    
    BASE_DIR = SERVERS_DIR.parent.parent.resolve()
    
    # Obtener información del sitio
    site_info = get_site_info(domain, BASE_DIR, console)
    
    if not site_info:
        console.print(f"[red]❌ Sitio '{domain}' no encontrado[/red]")
        console.print("[yellow]Usa 'lsxtool servers sites list' para ver sitios disponibles[/yellow]")
        return
    
    # Buscar archivo de configuración
    config_path = None
    if site_info.config_path and site_info.config_path != "N/A":
        config_path = Path(site_info.config_path)
        if not config_path.is_absolute():
            config_path = BASE_DIR / config_path
    else:
        # Buscar archivo de configuración
        apache_paths = [
            BASE_DIR / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
            BASE_DIR / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
        ]
        
        nginx_paths = [
            BASE_DIR / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            BASE_DIR / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
        ]
        
        for path in apache_paths + nginx_paths:
            if path.exists():
                config_path = path
                break
    
    if not config_path or not config_path.exists():
        console.print(f"[red]❌ No se encontró archivo de configuración para {domain}[/red]")
        return
    
    console.print(Panel.fit(f"[bold cyan]Gestión de Metadatos - {domain}[/bold cyan]", border_style="cyan"))
    
    # Leer metadatos actuales
    current_meta = parse_meta_from_conf(config_path)
    
    if current_meta:
        console.print("\n[bold]Metadatos actuales:[/bold]")
        meta_table = Table(show_header=False, box=None)
        meta_table.add_column("Campo", style="cyan", width=20)
        meta_table.add_column("Valor", style="green")
        
        for key, value in sorted(current_meta.items()):
            meta_table.add_row(key, value)
        
        console.print(meta_table)
    else:
        console.print("\n[yellow]⚠️ No hay metadatos configurados actualmente[/yellow]")
        current_meta = {}
    
    # Preguntar si actualizar
    if not Confirm.ask("\n¿Deseas actualizar los metadatos?", default=True):
        return
    
    # Importar catálogos
    from servers.sites.catalogs import (
        get_owners,
        get_providers,
        get_service_types,
        get_environments,
        get_backends,
        get_backend_versions
    )
    
    # Recopilar nuevos valores desde catálogos controlados
    console.print("\n[bold]Ingresa los metadatos desde catálogos controlados:[/bold]")
    
    # Owner desde catálogo
    owners_list = get_owners()
    console.print("\n[bold cyan]Equipos disponibles:[/bold cyan]")
    for idx, owner_item in enumerate(owners_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {owner_item}")
    
    owner_choice = Prompt.ask(
        "\n[bold]Selecciona Owner/Equipo responsable[/bold]",
        choices=[str(i) for i in range(1, len(owners_list) + 1)],
        default=str(1) if owners_list else None
    )
    owner = owners_list[int(owner_choice) - 1] if owner_choice else ""
    
    # Proveedor desde catálogo
    providers_list = get_providers()
    current_provider_idx = 0
    if current_meta.get("provider") in providers_list:
        current_provider_idx = providers_list.index(current_meta.get("provider")) + 1
    
    console.print("\n[bold cyan]Proveedores disponibles:[/bold cyan]")
    for idx, provider_item in enumerate(providers_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {provider_item}")
    
    provider_choice = Prompt.ask(
        "\n[bold]Selecciona Proveedor[/bold]",
        choices=[str(i) for i in range(1, len(providers_list) + 1)],
        default=str(current_provider_idx) if current_provider_idx > 0 else "1"
    )
    provider = providers_list[int(provider_choice) - 1]
    
    # Tipo de servicio desde catálogo
    service_types_list = get_service_types()
    current_service_type_idx = 0
    if current_meta.get("service_type") in service_types_list:
        current_service_type_idx = service_types_list.index(current_meta.get("service_type")) + 1
    
    console.print("\n[bold cyan]Tipos de servicio disponibles:[/bold cyan]")
    for idx, st_item in enumerate(service_types_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {st_item}")
    
    service_type_choice = Prompt.ask(
        "\n[bold]Selecciona Tipo de servicio[/bold]",
        choices=[str(i) for i in range(1, len(service_types_list) + 1)],
        default=str(current_service_type_idx) if current_service_type_idx > 0 else "1"
    )
    service_type = service_types_list[int(service_type_choice) - 1]
    
    # Ambiente desde catálogo
    environments_list = get_environments()
    current_env_idx = 0
    if current_meta.get("environment") in environments_list:
        current_env_idx = environments_list.index(current_meta.get("environment")) + 1
    
    console.print("\n[bold cyan]Ambientes disponibles:[/bold cyan]")
    for idx, env_item in enumerate(environments_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {env_item}")
    
    environment_choice = Prompt.ask(
        "\n[bold]Selecciona Ambiente[/bold]",
        choices=[str(i) for i in range(1, len(environments_list) + 1)],
        default=str(current_env_idx) if current_env_idx > 0 else "1"
    )
    environment = environments_list[int(environment_choice) - 1]
    
    # Backend desde catálogo
    backends_list = get_backends()
    current_backend = current_meta.get("backend", site_info.backend_type.lower())
    current_backend_idx = 0
    if current_backend in backends_list:
        current_backend_idx = backends_list.index(current_backend) + 1
    
    console.print("\n[bold cyan]Backends disponibles:[/bold cyan]")
    for idx, backend_item in enumerate(backends_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {backend_item}")
    
    backend_choice = Prompt.ask(
        "\n[bold]Selecciona Backend[/bold]",
        choices=[str(i) for i in range(1, len(backends_list) + 1)],
        default=str(current_backend_idx) if current_backend_idx > 0 else "1"
    )
    backend = backends_list[int(backend_choice) - 1]
    
    # Versión del backend - solo mostrar versiones disponibles
    backend_versions = get_backend_versions(backend)
    
    if backend_versions:
        console.print(f"\n[bold cyan]Versiones disponibles de {backend.upper()}:[/bold cyan]")
        for idx, version_item in enumerate(backend_versions, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {version_item}")
        
        current_version_idx = 0
        if current_meta.get("backend_version") in backend_versions:
            current_version_idx = backend_versions.index(current_meta.get("backend_version")) + 1
        
        version_choice = Prompt.ask(
            f"\n[bold]Selecciona Versión de {backend.upper()}[/bold]",
            choices=[str(i) for i in range(1, len(backend_versions) + 1)],
            default=str(current_version_idx) if current_version_idx > 0 else "1"
        )
        backend_version = backend_versions[int(version_choice) - 1]
    else:
        console.print(f"\n[yellow]⚠️ No se detectó versión de {backend.upper()} instalada[/yellow]")
        backend_version = Prompt.ask(
            f"Versión de {backend.upper()} (manual)",
            default=current_meta.get("backend_version", "")
        )
    
    # Construir dict de metadatos
    new_meta = {
        "owner": owner,
        "provider": provider,
        "service_type": service_type,
        "environment": environment,
        "backend": backend,
        "backend_version": backend_version
    }
    
    # Validar
    is_valid, warnings = validate_meta(new_meta, console)
    
    if warnings and not Confirm.ask("\n¿Continuar a pesar de las advertencias?", default=True):
        return
    
    # Escribir metadatos
    if write_meta_to_conf(config_path, new_meta, console):
        console.print(f"\n[bold green]✅ Metadatos actualizados para {domain}[/bold green]")
        console.print(f"[dim]Archivo: {config_path}[/dim]")
        
        # Mostrar resumen
        console.print("\n[bold]Metadatos actualizados:[/bold]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Campo", style="cyan", width=20)
        summary_table.add_column("Valor", style="green")
        
        for key, value in sorted(new_meta.items()):
            summary_table.add_row(key, value)
        
        console.print(summary_table)
        
        console.print(f"\n[yellow]💡 Ejecuta 'lsxtool servers sites info {domain}' para ver los cambios[/yellow]")
    else:
        console.print(f"\n[red]❌ Error al actualizar metadatos[/red]")
    
    console.print()
