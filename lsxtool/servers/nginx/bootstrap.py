"""
Bootstrap de bloque META para configuraciones Nginx
Solo se activa si NO existe bloque LSX META
Wizard interactivo para crear META completo
"""

import sys
from pathlib import Path
from typing import Dict, Optional, List
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from .parser import parse_nginx_config, find_nginx_configs
from ..sites.meta_parser import META_START, META_END, write_meta_to_conf
from ..declarative.bootstrap_helper import BootstrapHelper

# Imports con fallback
try:
    from ..sites.catalogs import (
        get_owners,
        get_providers,
        get_service_types,
        get_environments,
        get_backends,
        get_backend_versions,
        get_tech_providers,
        get_tech_managers,
    )
    from ..sites.server_version import get_nginx_version
    from ..sites.tech_versions import get_php_versions, get_node_versions, get_python_versions
except ImportError:
    # Fallback si los imports fallan
    import sys
    from pathlib import Path
    BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
    sys.path.insert(0, str(BASE_DIR))
    from servers.sites.catalogs import (
        get_owners,
        get_providers,
        get_service_types,
        get_environments,
        get_backends,
        get_backend_versions,
        get_tech_providers,
        get_tech_managers,
    )
    from servers.sites.server_version import get_nginx_version
    from servers.sites.tech_versions import get_php_versions, get_node_versions, get_python_versions

# Campos que no se muestran en "Campos META actuales" (solo tech y tech_version van en META)
META_DISPLAY_OMIT = frozenset({"tech_port", "upstream_ref"})


def bootstrap_nginx_meta(domain: str, base_dir: Path, console: Console, full_reconfigure: bool = False) -> bool:
    """
    Completa o crea bloque META (modo PATCH por defecto).
    
    - full_reconfigure=False (bootstrap): Solo completa campos obligatorios faltantes.
      Si META existe y falta tech_provider/tech_manager, wizard SOLO para esos campos.
    - full_reconfigure=True (reconfigure): Wizard completo para todos los campos.
    
    Args:
        domain: Dominio a configurar
        base_dir: Directorio base del proyecto
        console: Console de Rich para output
        full_reconfigure: Si True, solicita TODOS los campos (modo reconfigure)
    
    Returns:
        True si se procesó correctamente, False si no
    """
    # Inicializar helper declarativo
    helper = BootstrapHelper(base_dir, console)
    
    # Intentar cargar configuración declarativa (YAML)
    domain_config = helper.load_or_create_domain_config(domain)
    
    # Buscar archivo de configuración del dominio (legacy)
    config_files = find_nginx_configs(base_dir)
    
    config_file = None
    # Primero intentar coincidencia exacta
    for cf in config_files:
        if domain == cf.stem:
            config_file = cf
            break
    
    # Si no hay coincidencia exacta, buscar por prefijo (solo para prefijos simples)
    if not config_file:
        for cf in config_files:
            file_stem = cf.stem
            # Solo permitir búsqueda por prefijo si el dominio NO contiene puntos
            # (es un prefijo simple como "dev-identity")
            # Y el archivo comienza con el dominio seguido de un punto
            if "." not in domain and file_stem.startswith(domain + "."):
                config_file = cf
                break
    
    # Si no existe .conf, crearlo desde YAML si existe
    if not config_file and domain_config:
        console.print(f"[cyan]💡 Generando .conf desde configuración declarativa[/cyan]")
        if helper.generate_config_from_declarative(domain):
            # Re-buscar el archivo generado
            config_files = find_nginx_configs(base_dir)
            for cf in config_files:
                if domain == cf.stem:
                    config_file = cf
                    break
    
    if not config_file:
        console.print(f"[yellow]⚠️ No se encontró .conf para {domain}[/yellow]")
        console.print(f"[dim]Se creará durante el bootstrap[/dim]")
        # Crear ruta por defecto
        provider = domain_config.provider.lower() if domain_config else "external"
        env = (getattr(domain_config.environment, "value", domain_config.environment) or "dev") if domain_config else "dev"
        conf_dir = base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / provider / env
        conf_dir.mkdir(parents=True, exist_ok=True)
        config_file = conf_dir / f"{domain}.conf"
    
    # Verificar si ya existe META (legacy)
    config = parse_nginx_config(config_file) if config_file.exists() else None
    existing_meta = config.meta if config else {}
    
    # Si hay YAML, enriquecer metadata desde YAML (prioridad a YAML)
    if domain_config:
        # Convertir DomainConfig a meta dict para compatibilidad
        existing_meta = helper.enrich_from_declarative(domain, existing_meta)
        console.print(f"[green]✓[/green] Metadata enriquecida desde configuración declarativa")
    
    patch_only = False  # Solo wizard para campos faltantes (tech_provider, tech_manager)
    
    if existing_meta:
        # Detectar campos críticos faltantes
        missing_critical = _detect_missing_critical_fields(existing_meta)
        
        if missing_critical and not full_reconfigure:
            # META incompleto - modo PATCH: solo completar campos faltantes
            patch_only = True
            tech = existing_meta.get("tech", "").lower()
            tech_version = existing_meta.get("tech_version", "N/A")
            
            console.print(Panel.fit(
                f"[bold red]⚠️ META INCOMPLETO (Prioridad Alta)[/bold red]\n\n"
                f"Este servicio declara:\n"
                f"  [cyan]tech:[/cyan] {tech}\n"
                f"  [cyan]tech_version:[/cyan] {tech_version}\n\n"
                f"Faltan campos [bold]OBLIGATORIOS[/bold]:\n"
                + "\n".join([f"  [red]❌ {field}[/red]" for field in missing_critical]) + "\n\n"
                f"Estos campos son necesarios para:\n"
                f"  • Validar runtime correctamente\n"
                f"  • Futuras instalaciones y despliegues\n"
                f"  • Selección de imágenes/contenedores\n"
                f"  • CI/CD y onboarding\n\n"
                f"[bold]➡️ Se iniciará el asistente solo para completarlos.[/bold]",
                border_style="red"
            ))
            
            console.print()
            meta = existing_meta.copy()
        elif full_reconfigure:
            # Modo reconfigure: wizard completo, permitir redefinir todo
            console.print(Panel.fit(
                f"[bold yellow]Reconfiguración completa de META[/bold yellow]\n\n"
                f"[dim]Se solicitarán TODOS los campos META.[/dim]\n"
                f"[dim]Los valores actuales se mostrarán como referencia.[/dim]",
                border_style="yellow"
            ))
            console.print("\n[bold]Campos META actuales:[/bold]")
            for key, value in sorted(existing_meta.items()):
                if key in META_DISPLAY_OMIT:
                    continue
                console.print(f"  [cyan]{key}:[/cyan] {value}")
            console.print()
            meta = existing_meta.copy()
        else:
            # META completo, permitir edición opcional
            meta = existing_meta.copy()
            _normalize_meta_port_and_tech(meta)  # tech_port + inferir tech; no mostrar node_port
            console.print(Panel.fit(
                f"[bold yellow]⚠️ Bloque META ya existe[/bold yellow]\n\n"
                f"[dim]El archivo {config_file.name} ya contiene un bloque LSX META.[/dim]\n"
                f"[dim]Puedes actualizar campos o modificar valores existentes.[/dim]\n"
                f"[dim]Para reconfigurar todo: lsxtool servers reconfigure nginx {domain}[/dim]",
                border_style="yellow"
            ))
            console.print("\n[bold]Campos META actuales:[/bold]")
            for key, value in sorted(meta.items()):
                if key in META_DISPLAY_OMIT:
                    continue
                console.print(f"  [cyan]{key}:[/cyan] {value}")
            console.print()
            if not Confirm.ask("[bold yellow]¿Deseas actualizar/agregar campos?[/bold yellow]", default=True):
                console.print("[yellow]Operación cancelada[/yellow]")
                return False
    else:
        meta = {}
    
    console.print(Panel.fit(
        f"[bold cyan]Bootstrap de META para Nginx[/bold cyan]\n"
        f"[dim]Dominio:[/dim] {domain}\n"
        f"[dim]Archivo:[/dim] {config_file.name}",
        border_style="cyan"
    ))
    
    # Modo PATCH: solo wizard para tech_provider y tech_manager
    if patch_only:
        # Guardar en YAML también
        server_name = config.server_name if config else domain
        if helper.save_to_declarative(domain, meta, server_name):
            console.print(f"[green]✓[/green] Estado declarativo actualizado")
        return _run_patch_wizard(meta, config_file, domain, console)
    
    # Si hay YAML, mostrar qué campos ya están definidos
    if domain_config:
        console.print("\n[bold cyan]Campos definidos en YAML (no se preguntarán):[/bold cyan]")
        if domain_config.provider:
            console.print(f"  [green]✓[/green] provider: {domain_config.provider}")
        if domain_config.environment:
            env_val = getattr(domain_config.environment, "value", domain_config.environment)
            console.print(f"  [green]✓[/green] environment: {env_val}")
        upstream_ref = getattr(domain_config.server_web, "upstream_ref", None)
        if upstream_ref:
            console.print(f"  [green]✓[/green] upstream_ref: {upstream_ref}")
        if domain_config.server_web and domain_config.server_web.upstream:
            upstream = domain_config.server_web.upstream
            st_val = getattr(upstream.service_type, "value", upstream.service_type)
            tech_val = getattr(upstream.tech, "value", upstream.tech)
            console.print(f"  [green]✓[/green] service_type: {st_val}")
            console.print(f"  [green]✓[/green] tech: {tech_val}")
            console.print(f"  [green]✓[/green] tech_version: {upstream.tech_version}")
            if upstream.tech_provider:
                console.print(f"  [green]✓[/green] tech_provider: {upstream.tech_provider}")
            if upstream.tech_manager:
                console.print(f"  [green]✓[/green] tech_manager: {upstream.tech_manager}")
        console.print()
    
    if not existing_meta:
        console.print("\n[yellow]💡 Este wizard te guiará para crear el bloque META completo[/yellow]")
        if domain_config:
            console.print("[dim]Los campos ya definidos en YAML se usarán automáticamente[/dim]")
        else:
            console.print("[dim]Todos los campos son requeridos[/dim]")
        console.print()
    else:
        console.print("\n[yellow]💡 Actualizando campos META[/yellow]")
        console.print("[dim]Presiona Enter para mantener valores existentes[/dim]\n")

    # --- Normalizar puerto a tech_port e inferir tech desde claves antiguas ---
    _normalize_meta_port_and_tech(meta)

    # --- Resolver contexto y upstream por convención (SIN preguntar) ---
    # Provider real desde catálogo (lunarsystemx), no namespace interno (LSX)
    provider_ctx = meta.get("provider") or (domain_config.provider if domain_config else None) or "LSX"
    try:
        from ..declarative.catalog import resolve_provider_id
        provider_id = resolve_provider_id(base_dir, domain=domain, meta_provider=provider_ctx)
    except Exception:
        provider_id = provider_ctx
    if not provider_id:
        provider_id = provider_ctx
    env_ctx = meta.get("environment")
    if env_ctx is None and domain_config and domain_config.environment:
        env_ctx = getattr(domain_config.environment, "value", domain_config.environment)
    if not env_ctx and domain:
        if domain.startswith("dev-"):
            env_ctx = "dev"
        elif domain.startswith("qa-"):
            env_ctx = "qa"
        elif domain.startswith("prod-"):
            env_ctx = "prod"
        else:
            env_ctx = "dev"
    if not env_ctx:
        env_ctx = "dev"
    _st = domain_config.server_web.upstream.service_type if domain_config and domain_config.server_web and domain_config.server_web.upstream else None
    service_type_ctx = meta.get("service_type") or (getattr(_st, "value", _st) if _st else None) or "api"
    if hasattr(service_type_ctx, "value"):
        service_type_ctx = service_type_ctx.value
    slug_ctx = (domain_config.slug if domain_config else None) or meta.get("slug")
    if not slug_ctx and domain:
        slug_ctx = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "").split(".")[0]
    server_ctx = "nginx"
    upstream_auto_ref = None
    upstream_want_different_or_advanced = False
    upstream_missing = False
    upstream_compatibles = []
    if (service_type_ctx or "").lower() == "api" and slug_ctx:
        try:
            from ..declarative.upstream_convention import resolve_upstream_by_convention, expected_upstream_ref
            ref_used, path_used, compatibles = resolve_upstream_by_convention(
                base_dir, provider_ctx, server_ctx, env_ctx, service_type_ctx, slug_ctx, domain=domain
            )
            if ref_used and path_used:
                upstream_auto_ref = ref_used
                meta["upstream_ref"] = ref_used
                meta["provider"] = meta.get("provider") or provider_id
                meta["environment"] = meta.get("environment") or env_ctx
                meta["service_type"] = meta.get("service_type") or service_type_ctx
                # Puerto desde catálogo (tech_port genérico; no implica tech=node)
                try:
                    from ..declarative.upstream_loader import UpstreamCatalogLoader
                    catalog_loader = UpstreamCatalogLoader(base_dir, console)
                    catalog_def = catalog_loader.load(ref_used, provider=provider_id, server=server_ctx, environment=env_ctx)
                    if catalog_def and catalog_def.servers:
                        meta["tech_port"] = str(catalog_def.servers[0].port)
                except Exception:
                    pass
                console.print(f"\n[green]✓ Upstream detectado automáticamente:[/green] [cyan]{ref_used}[/cyan] [dim]({provider_id} / {server_ctx} / {env_ctx})[/dim]")
                upstream_want_different_or_advanced = Confirm.ask("¿Deseas usar un upstream diferente o configuración avanzada? [y/N]:", default=False)
            elif compatibles:
                upstream_compatibles = compatibles
            else:
                upstream_missing = True
        except Exception:
            upstream_missing = True

    # Wizard completo (full_reconfigure = re-preguntar todos los campos)
    # 1. Server web (quién atiende el dominio: nginx, apache, etc.)
    if "server_web" not in meta and "backend" not in meta:
        meta["server_web"] = "nginx"
        console.print(f"[green]✓[/green] Server web: [cyan]nginx[/cyan] (detectado automáticamente)")
    elif meta.get("server_web"):
        console.print(f"[green]✓[/green] Server web: [cyan]{meta['server_web']}[/cyan] (existente)")
    elif meta.get("backend"):
        meta["server_web"] = meta["backend"]
        console.print(f"[green]✓[/green] Server web: [cyan]{meta['server_web']}[/cyan] (existente, migrado desde backend)")
    else:
        meta["server_web"] = "nginx"
    
    # 2. Server web version (auto-detect)
    if ("server_web_version" not in meta and "backend_version" not in meta) or full_reconfigure:
        nginx_version = get_nginx_version()
        default_ver = meta.get("server_web_version") or meta.get("backend_version") if full_reconfigure else None
        if nginx_version:
            console.print(f"\n[bold]Versión del servidor web (Nginx):[/bold]")
            console.print(f"  [cyan]Detectada:[/cyan] {nginx_version}")
            if Confirm.ask("  ¿Usar esta versión?", default=True):
                meta["server_web_version"] = nginx_version
            else:
                meta["server_web_version"] = Prompt.ask("  Ingresa versión de Nginx", default=default_ver or "")
        else:
            meta["server_web_version"] = Prompt.ask("[bold]Versión de Nginx[/bold] (no detectada)", default=default_ver or "")
    elif not full_reconfigure:
        meta["server_web_version"] = meta.get("server_web_version") or meta.get("backend_version")
        console.print(f"[green]✓[/green] Server web version: [cyan]{meta.get('server_web_version', '')}[/cyan] (existente)")
    
    # 3. Environment
    if "environment" not in meta or full_reconfigure:
        environments = get_environments()
        console.print(f"\n[bold cyan]Ambiente:[/bold cyan]")
        for idx, env in enumerate(environments, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {env}")
        default_env = str(environments.index(meta["environment"]) + 1) if meta.get("environment") in environments else "1"
        env_choice = Prompt.ask(
            "  Selecciona ambiente",
            choices=[str(i) for i in range(1, len(environments) + 1)],
            default=default_env
        )
        meta["environment"] = environments[int(env_choice) - 1]
    elif not full_reconfigure:
        console.print(f"[green]✓[/green] Environment: [cyan]{meta['environment']}[/cyan] (existente)")
    
    # 4. Provider (solo preguntar si no está en YAML y no existe en meta)
    if "provider" not in meta or (full_reconfigure and not domain_config):
        providers = get_providers()
        console.print(f"\n[bold cyan]Proveedor:[/bold cyan]")
        for idx, p in enumerate(providers, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {p}")
        default_provider = str(providers.index(meta["provider"]) + 1) if meta.get("provider") in providers else "1"
        provider_choice = Prompt.ask(
            "  Selecciona proveedor",
            choices=[str(i) for i in range(1, len(providers) + 1)],
            default=default_provider
        )
        meta["provider"] = providers[int(provider_choice) - 1]
    elif domain_config and domain_config.provider:
        # Ya está en YAML, usar ese valor
        meta["provider"] = domain_config.provider
        console.print(f"[green]✓[/green] Provider: [cyan]{meta['provider']}[/cyan] (desde YAML)")
    else:
        console.print(f"[green]✓[/green] Provider: [cyan]{meta['provider']}[/cyan] (existente)")
    
    # 5. Owner (mapea a grupo del sistema)
    if "owner" not in meta or full_reconfigure:
        owners = get_owners()
        console.print(f"\n[bold cyan]Equipo responsable (owner → grupo del sistema):[/bold cyan]")
        for idx, owner in enumerate(owners, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {owner}")
        default_owner = str(owners.index(meta["owner"]) + 1) if meta.get("owner") in owners else "1"
        owner_choice = Prompt.ask(
            "  Selecciona equipo",
            choices=[str(i) for i in range(1, len(owners) + 1)],
            default=default_owner
        )
        meta["owner"] = owners[int(owner_choice) - 1]
    else:
        console.print(f"[green]✓[/green] Owner: [cyan]{meta['owner']}[/cyan] (existente)")

    # 5b. Usuario técnico (para ownership de /var/www y /var/log)
    if ("technical_user" not in meta or full_reconfigure) and meta.get("owner"):
        console.print(f"\n[bold cyan]Usuario técnico para ownership de FS:[/bold cyan]")
        console.print(f"  [dim]Se usará para chown de /var/www/... y /var/log/... (grupo = owner)[/dim]")
        technical_user = Prompt.ask(
            "  Usuario técnico (ej: michael.carrillo, vacío = usuario actual)",
            default=meta.get("technical_user") or ""
        )
        meta["technical_user"] = technical_user.strip() if technical_user else None
        if meta["technical_user"]:
            console.print(f"  [green]✓[/green] technical_user: [cyan]{meta['technical_user']}[/cyan]")
        else:
            console.print(f"  [dim]Se usará el usuario actual para ownership[/dim]")
    elif meta.get("technical_user"):
        console.print(f"[green]✓[/green] Technical user: [cyan]{meta['technical_user']}[/cyan] (existente)")
    
    # 6. Service type (solo preguntar si no está en YAML)
    if "service_type" not in meta or (full_reconfigure and not domain_config):
        service_types = get_service_types()
        console.print(f"\n[bold cyan]Tipo de servicio:[/bold cyan]")
        for idx, st in enumerate(service_types, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {st}")
        default_st = str(service_types.index(meta["service_type"]) + 1) if meta.get("service_type") in service_types else "1"
        st_choice = Prompt.ask(
            "  Selecciona tipo de servicio",
            choices=[str(i) for i in range(1, len(service_types) + 1)],
            default=default_st
        )
        meta["service_type"] = service_types[int(st_choice) - 1]
    elif domain_config and domain_config.server_web and domain_config.server_web.upstream:
        _st = domain_config.server_web.upstream.service_type
        meta["service_type"] = getattr(_st, "value", _st)
        console.print(f"[green]✓[/green] Service type: [cyan]{meta['service_type']}[/cyan] (desde YAML)")
    else:
        console.print(f"[green]✓[/green] Service type: [cyan]{meta['service_type']}[/cyan] (existente)")
    
    # 7. Tech (solo preguntar si no está en YAML)
    if "tech" not in meta:
        # Verificar si está en YAML
        if domain_config and domain_config.server_web and domain_config.server_web.upstream:
            up = domain_config.server_web.upstream
            meta["tech"] = getattr(up.tech, "value", up.tech)
            meta["tech_version"] = up.tech_version
            meta["tech_provider"] = getattr(up.tech_provider, "value", up.tech_provider)
            meta["tech_manager"] = getattr(up.tech_manager, "value", up.tech_manager)
            meta["tech_port"] = str(up.port)
            console.print(f"\n[green]✓[/green] Tech: [cyan]{meta['tech'].upper()}[/cyan] (desde YAML)")
            console.print(f"[green]✓[/green] Tech version: [cyan]{meta['tech_version']}[/cyan] (desde YAML)")
            console.print(f"[green]✓[/green] Tech provider: [cyan]{meta['tech_provider']}[/cyan] (desde YAML)")
            console.print(f"[green]✓[/green] Tech manager: [cyan]{meta['tech_manager']}[/cyan] (desde YAML)")
            tech_choice = "1" if meta["tech"] == "php" else ("2" if meta["tech"] == "node" else ("3" if meta["tech"] == "python" else "4"))
        else:
            console.print(f"\n[bold cyan]Tecnología:[/bold cyan]")
            console.print("  [cyan]1.[/cyan] php")
            console.print("  [cyan]2.[/cyan] node")
            console.print("  [cyan]3.[/cyan] python")
            console.print("  [cyan]4.[/cyan] Ninguna / Otro")
            tech_choice = Prompt.ask(
                "  Selecciona tecnología",
                choices=["1", "2", "3", "4"],
                default="4"
            )
            
            tech_map = {"1": "php", "2": "node", "3": "python"}
            if tech_choice != "4":
                meta["tech"] = tech_map[tech_choice]
    else:
        tech_display = meta["tech"].upper()
        console.print(f"\n[green]✓[/green] Tech: [cyan]{tech_display}[/cyan] (existente)")
        tech_choice = "1" if meta["tech"] == "php" else ("2" if meta["tech"] == "node" else ("3" if meta["tech"] == "python" else "4"))
    
    # Si tech está presente (existente o nuevo), validar tech_provider y tech_manager
    # PRIORIZAR campos faltantes críticos
    if meta.get("tech"):
        tech = meta["tech"]
        
        # Verificar si faltan campos críticos
        missing_provider = "tech_provider" not in meta
        missing_manager = "tech_manager" not in meta
        
        if missing_provider or missing_manager:
            # Mostrar mensaje de prioridad
            console.print(f"\n[bold red]⚠️ Campos obligatorios faltantes para {tech.upper()}[/bold red]")
            if missing_provider:
                console.print(f"  [red]❌ tech_provider[/red] - Define cómo se gestiona la versión de {tech}")
            if missing_manager:
                console.print(f"  [red]❌ tech_manager[/red] - Define el gestor de paquetes")
            console.print()
        
        tech = meta["tech"]
        
        # 8. Tech version (solo si no está en YAML)
        if "tech_version" not in meta and not (domain_config and domain_config.server_web and domain_config.server_web.upstream):
            versions = []
            if tech == "php":
                versions = get_php_versions()
            elif tech == "node":
                versions = get_node_versions()
            elif tech == "python":
                versions = get_python_versions()
            
            if versions:
                console.print(f"\n[bold]Versión de {tech.upper()}:[/bold]")
                console.print(f"  [cyan]Detectadas:[/cyan] {', '.join(versions)}")
                for idx, version in enumerate(versions, 1):
                    console.print(f"  [cyan]{idx}.[/cyan] {version}")
                version_choice = Prompt.ask(
                    "  Selecciona versión",
                    choices=[str(i) for i in range(1, len(versions) + 1)],
                    default="1"
                )
                meta["tech_version"] = versions[int(version_choice) - 1]
            else:
                meta["tech_version"] = Prompt.ask(f"  Versión de {tech.upper()} (no detectada)")
        elif domain_config and domain_config.server_web and domain_config.server_web.upstream:
            pass
        else:
            console.print(f"[green]✓[/green] Tech version: [cyan]{meta['tech_version']}[/cyan] (existente)")
        
        # 8b. Tech Provider (OBLIGATORIO cuando tech está presente)
        if "tech_provider" not in meta and not (domain_config and domain_config.server_web and domain_config.server_web.upstream and domain_config.server_web.upstream.tech_provider):
            console.print(f"\n[bold red]Tech Provider para {tech.upper()} (OBLIGATORIO):[/bold red]")
            console.print(f"[yellow]💡 Este campo es OBLIGATORIO y define cómo se gestiona la versión de {tech}[/yellow]")
            console.print(f"[dim]Sin este campo, el servicio queda en estado inválido[/dim]\n")
            
            valid_providers = get_tech_providers(tech)
            detected_providers = _detect_tech_providers(tech, valid_providers)
            
            if detected_providers:
                console.print(f"  [cyan]Detectados en el sistema:[/cyan] {', '.join(detected_providers)}")
                console.print(f"  [dim](Estos son solo sugerencias, debes seleccionar explícitamente)[/dim]\n")
            
            console.print(f"  [cyan]Opciones válidas:[/cyan]")
            for idx, provider in enumerate(valid_providers, 1):
                marker = " [yellow]★[/yellow]" if provider in detected_providers else ""
                console.print(f"    [cyan]{idx}.[/cyan] {provider}{marker}")
            
            provider_choice = Prompt.ask(
                "  Selecciona tech_provider",
                choices=[str(i) for i in range(1, len(valid_providers) + 1)],
                default="1" if valid_providers else None
            )
            meta["tech_provider"] = valid_providers[int(provider_choice) - 1]
            console.print(f"  [green]✓[/green] tech_provider configurado: [cyan]{meta['tech_provider']}[/cyan]")
        else:
            console.print(f"[green]✓[/green] Tech provider: [cyan]{meta['tech_provider']}[/cyan] (existente)")
        
        # 8c. Tech Manager (OBLIGATORIO cuando tech está presente)
        if "tech_manager" not in meta and not (domain_config and domain_config.server_web and domain_config.server_web.upstream and domain_config.server_web.upstream.tech_manager):
            console.print(f"\n[bold red]Tech Manager para {tech.upper()} (OBLIGATORIO):[/bold red]")
            console.print(f"[yellow]💡 Este campo es OBLIGATORIO y define el gestor de paquetes[/yellow]")
            console.print(f"[dim]Sin este campo, el servicio queda en estado inválido[/dim]\n")
            
            valid_managers = get_tech_managers(tech)
            detected_managers = _detect_tech_managers(tech, valid_managers)
            
            if detected_managers:
                console.print(f"  [cyan]Detectados en el sistema:[/cyan] {', '.join(detected_managers)}")
                console.print(f"  [dim](Estos son solo sugerencias, debes seleccionar explícitamente)[/dim]\n")
            
            console.print(f"  [cyan]Opciones válidas:[/cyan]")
            for idx, manager in enumerate(valid_managers, 1):
                marker = " [yellow]★[/yellow]" if manager in detected_managers else ""
                console.print(f"    [cyan]{idx}.[/cyan] {manager}{marker}")
            
            manager_choice = Prompt.ask(
                "  Selecciona tech_manager",
                choices=[str(i) for i in range(1, len(valid_managers) + 1)],
                default="1" if valid_managers else None
            )
            meta["tech_manager"] = valid_managers[int(manager_choice) - 1]
            console.print(f"  [green]✓[/green] tech_manager configurado: [cyan]{meta['tech_manager']}[/cyan]")
        else:
            console.print(f"[green]✓[/green] Tech manager: [cyan]{meta['tech_manager']}[/cyan] (existente)")
        
        # 9. Upstream: solo si no se resolvió por convención o usuario pidió diferente/avanzado
        if meta["service_type"] == "api":
            if upstream_auto_ref and not upstream_want_different_or_advanced:
                console.print(f"[green]✓[/green] Upstream: [cyan]{meta['upstream_ref']}[/cyan] (por convención)")
            elif upstream_missing:
                try:
                    from ..declarative.upstream_convention import convention_dir, expected_upstream_ref
                    from ..declarative.upstream_loader import UpstreamCatalogLoader
                    from ..declarative.upstream_catalog import UpstreamCatalogDef, UpstreamServerEntry
                    console.print(f"\n[yellow]⚠️ No se encontró upstream para:[/yellow]")
                    console.print(f"  [dim]{provider_id} / {server_ctx} / {env_ctx} / {service_type_ctx} / {slug_ctx}[/dim]")
                    console.print("\n[cyan]Opciones:[/cyan]")
                    console.print("  [cyan]1.[/cyan] Crear upstream estándar (recomendado)")
                    console.print("  [cyan]2.[/cyan] Seleccionar upstream existente")
                    console.print("  [cyan]3.[/cyan] Cancelar")
                    opt = Prompt.ask("  Selecciona", choices=["1", "2", "3"], default="1")
                    if opt == "1":
                        ref_expected = expected_upstream_ref(service_type_ctx, slug_ctx)
                        port = int(meta.get("tech_port") or meta.get("node_port") or Prompt.ask("  Puerto de la aplicación", default="3000"))
                        defn = UpstreamCatalogDef(
                            name=ref_expected,
                            type="single",
                            protocol="http",
                            servers=[UpstreamServerEntry(host="127.0.0.1", port=port)],
                        )
                        loader = UpstreamCatalogLoader(base_dir, console)
                        if loader.save(defn, to_convention=(provider_id, server_ctx, env_ctx)):
                            meta["upstream_ref"] = ref_expected
                            console.print(f"  [green]✓[/green] Upstream creado: [cyan]{ref_expected}[/cyan]")
                        else:
                            meta["tech_port"] = str(port)
                    elif opt == "2":
                        catalog = UpstreamCatalogLoader(base_dir, console)
                        names = catalog.list_names()
                        conv_dir = convention_dir(base_dir, provider_id, server_ctx, env_ctx)
                        for p in sorted(conv_dir.glob("*.yaml")):
                            if p.stem not in names:
                                names.append(p.stem)
                        names = sorted(set(names))
                        if not names:
                            console.print("  [yellow]No hay upstreams. Usando puerto inline.[/yellow]")
                            meta["tech_port"] = Prompt.ask("  Puerto de la aplicación", default="3000")
                        else:
                            for i, n in enumerate(names, 1):
                                console.print(f"    [cyan]{i}.[/cyan] {n}")
                            choice = Prompt.ask("  Selecciona upstream", choices=[str(i) for i in range(1, len(names) + 1)], default="1")
                            meta["upstream_ref"] = names[int(choice) - 1]
                    else:
                        meta["tech_port"] = Prompt.ask("  Puerto de la aplicación", default="3000")
                except Exception:
                    meta["tech_port"] = Prompt.ask("  Puerto de la aplicación", default="3000")
            elif upstream_compatibles:
                console.print("\n[yellow]⚠️ Se encontraron múltiples upstreams compatibles:[/yellow]")
                for i, n in enumerate(upstream_compatibles, 1):
                    console.print(f"  [cyan]{i}.[/cyan] {n}")
                choice = Prompt.ask("  Selecciona upstream", choices=[str(i) for i in range(1, len(upstream_compatibles) + 1)], default="1")
                meta["upstream_ref"] = upstream_compatibles[int(choice) - 1]
            elif upstream_want_different_or_advanced:
                try:
                    from ..declarative.upstream_convention import convention_dir
                    from ..declarative.upstream_loader import UpstreamCatalogLoader
                    catalog = UpstreamCatalogLoader(base_dir, console)
                    names = catalog.list_names()
                    conv_dir = convention_dir(base_dir, provider_id, server_ctx, env_ctx)
                    for p in sorted(conv_dir.glob("*.yaml")):
                        if p.stem not in names:
                            names.append(p.stem)
                    names = sorted(set(names))
                    if names:
                        console.print("  [cyan]Upstreams disponibles:[/cyan]")
                        for i, n in enumerate(names, 1):
                            console.print(f"    [cyan]{i}.[/cyan] {n}")
                        choice = Prompt.ask("  Selecciona upstream (o Enter para mantener actual)", choices=[str(i) for i in range(1, len(names) + 1)] + [""], default="")
                        if choice:
                            meta["upstream_ref"] = names[int(choice) - 1]
                    else:
                        meta["tech_port"] = Prompt.ask("  Puerto de la aplicación", default="3000")
                except Exception:
                    meta["tech_port"] = Prompt.ask("  Puerto de la aplicación", default="3000")
            elif not meta.get("upstream_ref"):
                meta["tech_port"] = Prompt.ask("  Puerto de la aplicación", default="3000")
    
    # Mostrar resumen
    console.print("\n[bold]Resumen de META:[/bold]")
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Campo", style="cyan", width=20)
    summary_table.add_column("Valor", style="green")
    
    for key, value in sorted(meta.items()):
        summary_table.add_row(key, value)
    
    console.print(summary_table)
    
    # Confirmación
    console.print()
    if not Confirm.ask("[bold yellow]¿Crear bloque META con estos valores?[/bold yellow]", default=True):
        console.print("[yellow]Operación cancelada[/yellow]")
        return False

    # Backup del .conf si existe
    if config_file.exists():
        from datetime import datetime
        backup_path = config_file.parent / f"{config_file.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        try:
            import shutil
            shutil.copy2(config_file, backup_path)
            console.print(f"[dim]Backup: {backup_path.name}[/dim]")
        except Exception as e:
            console.print(f"[yellow]⚠ No se pudo crear backup: {e}[/yellow]")

    # Guardar en YAML declarativo (fuente de verdad). No escribimos META al .conf aquí;
    # el .conf se genera solo desde YAML, así actual y regenerado coinciden y no hay diff espurio.
    server_name = config.server_name if config else domain
    if not helper.save_to_declarative(domain, meta, server_name):
        console.print(f"[yellow]⚠️ No se pudo guardar estado declarativo (continuando...)[/yellow]")
    else:
        console.print(f"[green]✅ Estado declarativo guardado en YAML[/green]")

    # Orquestación: usuarios/grupos, filesystem, permisos
    provider_ctx = meta.get("provider", "").lower()
    env_ctx = meta.get("environment", "dev")
    slug_ctx = meta.get("slug") or domain.replace("dev-", "").replace("qa-", "").replace("prod-", "").split(".")[0]
    owner_ctx = meta.get("owner")
    technical_user_ctx = meta.get("technical_user") or None
    if provider_ctx and slug_ctx and owner_ctx:
        console.print()
        try:
            from ..orchestration import run_bootstrap_orchestration
            run_bootstrap_orchestration(
                provider_ctx,
                env_ctx,
                slug_ctx,
                owner_ctx,
                technical_user_ctx,
                base_dir,
                console,
                dry_run=False,
            )
        except Exception as e:
            console.print(Panel.fit(
                f"[bold red]❌ Orquestación de sistema falló[/bold red]\n\n"
                f"[red]{e}[/red]\n\n"
                f"El orquestador debía: crear grupo [cyan]{owner_ctx}[/cyan], usuario técnico, "
                f"/var/www y /var/log con permisos.\n"
                f"[dim]Sin esto tendrás que crear usuarios, directorios y permisos manualmente.[/dim]",
                border_style="red"
            ))
            if not Confirm.ask("\n[bold yellow]¿Continuar de todos modos (crearás usuarios/permisos después)?[/bold yellow] [y/N]", default=False):
                console.print("[yellow]Bootstrap abortado. Corrige el error y vuelve a ejecutar.[/yellow]")
                return False
            console.print("[dim]Continuando sin orquestación completada.[/dim]")
    else:
        console.print("[dim]ℹ Owner/provider/slug incompletos: orquestación de FS omitida.[/dim]")

    # Generar .conf desde YAML y comparar con actual (sin haber escrito META antes).
    domain_config_after = helper.loader.get_domain(domain)
    if not domain_config_after:
        console.print(f"[yellow]⚠ No hay configuración declarativa para {domain}; no se generó .conf.[/yellow]")
        return True

    new_content = helper.generator.generate_nginx_config(domain_config_after)
    if not new_content:
        console.print(f"[yellow]⚠ No se pudo regenerar .conf desde YAML.[/yellow]")
        return True

    if config_file.exists():
        import difflib
        old_lines = config_file.read_text().splitlines()
        new_lines = new_content.splitlines()
        diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile="actual", tofile="regenerado", lineterm="", n=2))
        if diff_lines:
            console.print("\n[bold]Diff (actual → regenerado):[/bold]")
            for line in diff_lines[:80]:
                if line.startswith("+"):
                    console.print(f"[green]{line}[/green]")
                elif line.startswith("-"):
                    console.print(f"[red]{line}[/red]")
                else:
                    console.print(f"[dim]{line}[/dim]")
            if len(diff_lines) > 80:
                console.print("[dim]... (más líneas)[/dim]")
            if not Confirm.ask("\n[bold yellow]¿Aplicar configuración regenerada?[/bold yellow]", default=True):
                console.print("[dim]Configuración no regenerada (puedes ejecutar 'lsxtool servers apply' después)[/dim]")
            else:
                config_file.write_text(new_content)
                console.print(f"[green]✅ Configuración Nginx generada/actualizada (root y paths declarados)[/green]")
        else:
            console.print("[dim]Sin cambios en .conf[/dim]")
    else:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(new_content)
        console.print(f"[green]✅ Configuración Nginx generada: {config_file}[/green]")

    return True


def _normalize_meta_port_and_tech(meta: Dict[str, str]) -> None:
    """
    Normaliza puerto a tech_port e infiere tech desde claves antiguas (node_port, php_port, python_port).
    Así no mostramos 'node_port' (que implica tech=node) y no preguntamos tech si ya se infirió.
    """
    if "node_port" in meta and meta.get("node_port"):
        if "tech_port" not in meta or not meta.get("tech_port"):
            meta["tech_port"] = meta["node_port"]
        if "tech" not in meta:
            meta["tech"] = "node"
        del meta["node_port"]
    if "php_port" in meta and meta.get("php_port"):
        if "tech_port" not in meta or not meta.get("tech_port"):
            meta["tech_port"] = meta["php_port"]
        if "tech" not in meta:
            meta["tech"] = "php"
        del meta["php_port"]
    if "python_port" in meta and meta.get("python_port"):
        if "tech_port" not in meta or not meta.get("tech_port"):
            meta["tech_port"] = meta["python_port"]
        if "tech" not in meta:
            meta["tech"] = "python"
        del meta["python_port"]


def _run_patch_wizard(meta: Dict[str, str], config_file: Path, domain: str, console: Console) -> bool:
    """
    Wizard SOLO para campos críticos faltantes (tech_provider, tech_manager).
    No pregunta backend, provider, environment, etc.
    """
    try:
        from ..sites.catalogs import get_tech_providers, get_tech_managers
    except ImportError:
        BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from servers.sites.catalogs import get_tech_providers, get_tech_managers
    
    tech = meta.get("tech", "").lower()
    if not tech:
        console.print("[red]❌ No se puede completar: falta 'tech' en META[/red]")
        return False
    
    # tech_provider
    if "tech_provider" not in meta:
        console.print(f"\n[bold red]Tech Provider para {tech.upper()} (OBLIGATORIO):[/bold red]")
        valid_providers = get_tech_providers(tech)
        detected_providers = _detect_tech_providers(tech, valid_providers)
        if detected_providers:
            console.print(f"  [cyan]Detectados en el sistema:[/cyan] {', '.join(detected_providers)}")
            console.print(f"  [dim](Solo sugerencias, debes seleccionar explícitamente)[/dim]\n")
        console.print(f"  [cyan]Opciones válidas:[/cyan]")
        for idx, provider in enumerate(valid_providers, 1):
            marker = " [yellow]★[/yellow]" if provider in detected_providers else ""
            console.print(f"    [cyan]{idx}.[/cyan] {provider}{marker}")
        provider_choice = Prompt.ask(
            "  Selecciona tech_provider",
            choices=[str(i) for i in range(1, len(valid_providers) + 1)],
            default="1" if valid_providers else None
        )
        meta["tech_provider"] = valid_providers[int(provider_choice) - 1]
        console.print(f"  [green]✓[/green] tech_provider: [cyan]{meta['tech_provider']}[/cyan]")
    
    # tech_manager
    if "tech_manager" not in meta:
        console.print(f"\n[bold red]Tech Manager para {tech.upper()} (OBLIGATORIO):[/bold red]")
        valid_managers = get_tech_managers(tech)
        detected_managers = _detect_tech_managers(tech, valid_managers)
        if detected_managers:
            console.print(f"  [cyan]Detectados en el sistema:[/cyan] {', '.join(detected_managers)}")
            console.print(f"  [dim](Solo sugerencias, debes seleccionar explícitamente)[/dim]\n")
        console.print(f"  [cyan]Opciones válidas:[/cyan]")
        for idx, manager in enumerate(valid_managers, 1):
            marker = " [yellow]★[/yellow]" if manager in detected_managers else ""
            console.print(f"    [cyan]{idx}.[/cyan] {manager}{marker}")
        manager_choice = Prompt.ask(
            "  Selecciona tech_manager",
            choices=[str(i) for i in range(1, len(valid_managers) + 1)],
            default="1" if valid_managers else None
        )
        meta["tech_manager"] = valid_managers[int(manager_choice) - 1]
        console.print(f"  [green]✓[/green] tech_manager: [cyan]{meta['tech_manager']}[/cyan]")
    
    # Resumen y guardar
    console.print("\n[bold]Campos agregados/actualizados:[/bold]")
    for key in ["tech_provider", "tech_manager"]:
        if key in meta:
            console.print(f"  [cyan]{key}:[/cyan] {meta[key]}")
    console.print()
    if not Confirm.ask("[bold yellow]¿Guardar en META?[/bold yellow]", default=True):
        console.print("[yellow]Operación cancelada[/yellow]")
        return False
    
    if write_meta_to_conf(config_file, meta, console):
        console.print(f"\n[green]✅ META actualizado correctamente[/green]")
        console.print(f"[dim]Archivo: {config_file}[/dim]")
        return True
    console.print(f"\n[red]❌ Error al escribir META[/red]")
    return False


def _detect_missing_critical_fields(meta: Dict[str, str]) -> List[str]:
    """
    Detecta campos críticos faltantes en META
    
    Cuando tech está presente, tech_provider y tech_manager son obligatorios
    
    Returns:
        Lista de nombres de campos críticos faltantes
    """
    missing = []
    
    tech = meta.get("tech", "").lower()
    if tech:
        # Si tech está presente, tech_provider y tech_manager son obligatorios
        if "tech_provider" not in meta:
            missing.append("tech_provider")
        if "tech_manager" not in meta:
            missing.append("tech_manager")
    
    return missing


def _detect_tech_providers(tech: str, valid_providers: list) -> list:
    """
    Detecta tech_providers instalados en el sistema
    SOLO para sugerencia UX, NUNCA para autoasignar
    
    Returns:
        Lista de tech_providers detectados que están en valid_providers
    """
    detected = []
    tech_lower = tech.lower()
    import shutil
    import os
    from pathlib import Path
    
    if tech_lower == "node":
        if "volta" in valid_providers and shutil.which("volta"):
            detected.append("volta")
        if "nvm" in valid_providers and (os.environ.get("NVM_DIR") or (Path.home() / ".nvm").exists()):
            detected.append("nvm")
        if "asdf" in valid_providers and shutil.which("asdf") and os.environ.get("ASDF_DATA_DIR"):
            detected.append("asdf")
        if "system" in valid_providers:
            detected.append("system")
    elif tech_lower == "php":
        if "phpbrew" in valid_providers and shutil.which("phpbrew"):
            detected.append("phpbrew")
        if "system" in valid_providers:
            detected.append("system")
    elif tech_lower == "python":
        if "pyenv" in valid_providers and shutil.which("pyenv"):
            detected.append("pyenv")
        if "asdf" in valid_providers and shutil.which("asdf") and os.environ.get("ASDF_DATA_DIR"):
            detected.append("asdf")
        if "system" in valid_providers:
            detected.append("system")
    
    return detected


def _detect_tech_managers(tech: str, valid_managers: list) -> list:
    """
    Detecta tech_managers instalados en el sistema
    SOLO para sugerencia UX, NUNCA para autoasignar
    
    Returns:
        Lista de tech_managers detectados que están en valid_managers
    """
    detected = []
    tech_lower = tech.lower()
    import shutil
    
    if tech_lower == "node":
        if "npm" in valid_managers and shutil.which("npm"):
            detected.append("npm")
        if "yarn" in valid_managers and shutil.which("yarn"):
            detected.append("yarn")
        if "pnpm" in valid_managers and shutil.which("pnpm"):
            detected.append("pnpm")
        if "bun" in valid_managers and shutil.which("bun"):
            detected.append("bun")
    elif tech_lower == "php":
        if "composer" in valid_managers and shutil.which("composer"):
            detected.append("composer")
    elif tech_lower == "python":
        if "pip" in valid_managers and shutil.which("pip"):
            detected.append("pip")
        if "poetry" in valid_managers and shutil.which("poetry"):
            detected.append("poetry")
    
    return detected
