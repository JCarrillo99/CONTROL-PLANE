"""
Migración de .conf legacy a sistema declarativo
Convierte .conf existentes → YAML
"""

from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .loader import DeclarativeLoader
from .models import DomainConfig, ServerWebConfig, UpstreamConfig, ServerWebType, TechType, ServiceType, Environment, DomainType
from .generator import ConfigGenerator
from ..nginx.parser import find_nginx_configs, parse_nginx_config


class LegacyMigrator:
    """Migra configuraciones legacy (.conf) a sistema declarativo (YAML)"""
    
    def __init__(self, base_dir: Path, console: Optional[Console] = None):
        self.base_dir = base_dir
        self.console = console or Console()
        self.loader = DeclarativeLoader(base_dir, console)
    
    def migrate_all(self, dry_run: bool = False) -> int:
        """
        Migra todos los .conf encontrados a YAML
        
        Args:
            dry_run: Si True, solo muestra qué se migraría sin guardar
        
        Returns:
            Número de dominios migrados
        """
        self.console.print(Panel.fit(
            "[bold cyan]Migración Legacy → Declarativo[/bold cyan]\n\n"
            f"[dim]Modo: {'DRY RUN (no guarda)' if dry_run else 'MIGRACIÓN REAL'}[/dim]",
            border_style="cyan"
        ))
        
        config_files = find_nginx_configs(self.base_dir)
        
        if not config_files:
            self.console.print("[yellow]⚠️ No se encontraron archivos .conf[/yellow]")
            return 0
        
        self.console.print(f"\n[cyan]Archivos .conf encontrados: {len(config_files)}[/cyan]\n")
        
        migrated = 0
        skipped = 0
        errors = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Migrando...", total=len(config_files))
            
            for config_file in config_files:
                domain = config_file.stem
                progress.update(task, description=f"Migrando {domain}...")
                
                # Verificar si ya existe YAML
                if self.loader.get_domain(domain):
                    skipped += 1
                    progress.update(task, advance=1)
                    continue
                
                # Parsear .conf
                nginx_config = parse_nginx_config(config_file)
                if not nginx_config or not nginx_config.meta:
                    errors += 1
                    progress.update(task, advance=1)
                    continue
                
                # Convertir a DomainConfig
                domain_config = self._conf_to_domain_config(domain, nginx_config)
                if not domain_config:
                    errors += 1
                    progress.update(task, advance=1)
                    continue
                
                # Guardar (si no es dry_run)
                if not dry_run:
                    if self.loader.save_domain(domain_config):
                        migrated += 1
                    else:
                        errors += 1
                else:
                    migrated += 1
                
                progress.update(task, advance=1)
        
        # Resumen
        self.console.print(f"\n[bold]Resumen:[/bold]")
        self.console.print(f"  [green]Migrados:[/green] {migrated}")
        self.console.print(f"  [yellow]Omitidos (ya existen):[/yellow] {skipped}")
        self.console.print(f"  [red]Errores:[/red] {errors}")
        
        if dry_run:
            self.console.print(f"\n[yellow]💡 Ejecuta sin --dry-run para aplicar la migración[/yellow]")
        
        return migrated
    
    def _conf_to_domain_config(self, domain: str, nginx_config) -> Optional[DomainConfig]:
        """Convierte NginxConfig a DomainConfig"""
        meta = nginx_config.meta
        
        # Inferir tipo de dominio
        domain_type = DomainType.SUBDOMAIN if domain.count(".") >= 2 else DomainType.ROOT
        
        # Inferir slug
        domain_clean = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "")
        slug = domain_clean.split(".")[0]
        
        # server_web (compat: meta puede tener "backend" o "server_web")
        sw_type = meta.get("server_web") or meta.get("backend") or "nginx"
        if isinstance(sw_type, dict):
            sw_type = (sw_type.get("type") or "nginx").lower()
        else:
            sw_type = (sw_type or "nginx").lower()
        server_web_config = ServerWebConfig(type=sw_type)
        if meta.get("upstream_ref"):
            server_web_config.upstream_ref = meta["upstream_ref"].strip()
            server_web_config.upstream = None
        
        # Upstream inline (si es API y no hay upstream_ref)
        service_type = meta.get("service_type", "").lower()
        if service_type == "api" and meta.get("tech") and not server_web_config.upstream_ref:
            tech = meta.get("tech", "").lower()
            port = int(
                meta.get("tech_port")
                or meta.get("node_port")
                or meta.get("php_port")
                or meta.get("python_port")
                or 3000
            )
            
            upstream = UpstreamConfig(
                service_type=ServiceType(service_type),
                tech=TechType(tech),
                tech_version=meta.get("tech_version", ""),
                tech_provider=meta.get("tech_provider", "system").lower(),
                tech_manager=meta.get("tech_manager", "npm").lower(),
                port=port
            )
            server_web_config.upstream = upstream
        
        # Construir DomainConfig
        try:
            domain_config = DomainConfig(
                domain=domain,
                type=domain_type,
                slug=slug,
                environment=Environment(meta.get("environment", "dev").lower()),
                provider=meta.get("provider", "EXTERNAL"),
                server=meta.get("server"),
                server_web=server_web_config,
                owner=meta.get("owner"),
                technical_user=meta.get("technical_user"),
                description=meta.get("description")
            )
            return domain_config
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al convertir {domain}: {e}[/red]")
            return None


def migrate_legacy(base_dir: Path, console: Console, dry_run: bool = False) -> int:
    """Función helper para migración desde CLI"""
    migrator = LegacyMigrator(base_dir, console)
    return migrator.migrate_all(dry_run=dry_run)
