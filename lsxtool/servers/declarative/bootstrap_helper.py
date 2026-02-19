"""
Helper para bootstrap que integra sistema declarativo
Lee YAML primero, solo pregunta lo faltante
"""

from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.prompt import Prompt, Confirm

from .loader import DeclarativeLoader
from .models import DomainConfig, ServerWebConfig, UpstreamConfig, ServerWebType, TechType, ServiceType, Environment
from .generator import ConfigGenerator


class BootstrapHelper:
    """Helper para bootstrap que integra YAML declarativo"""
    
    def __init__(self, base_dir: Path, console: Console):
        self.base_dir = base_dir
        self.console = console
        self.loader = DeclarativeLoader(base_dir, console)
        self.generator = ConfigGenerator(base_dir, console)
    
    def load_or_create_domain_config(self, domain: str) -> Optional[DomainConfig]:
        """
        Carga configuración declarativa existente o crea una nueva
        
        Args:
            domain: Dominio a configurar
        
        Returns:
            DomainConfig o None si hay error
        """
        # Intentar cargar YAML existente
        self.loader.load_all()
        existing = self.loader.get_domain(domain)
        
        if existing:
            self.console.print(f"[green]✓[/green] Configuración declarativa encontrada para {domain}")
            return existing
        
        # No existe, retornar None para que bootstrap cree una nueva
        return None
    
    def enrich_from_declarative(self, domain: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriquece metadata desde configuración declarativa
        
        Args:
            domain: Dominio
            meta: Metadata actual (puede estar vacía)
        
        Returns:
            Metadata enriquecida
        """
        # Cargar estado declarativo
        self.loader.load_all()
        domain_config = self.loader.get_domain(domain)
        defaults = self.loader.get_defaults()
        
        if not domain_config:
            # No hay YAML, usar defaults globales
            if defaults:
                meta.update(defaults)
            return meta
        
        # Hay YAML, usar valores declarativos
        # NO sobreescribir si ya existen en meta (prioridad a lo que el usuario ya configuró)
        if "provider" not in meta:
            meta["provider"] = domain_config.provider
        
        if "environment" not in meta:
            meta["environment"] = domain_config.environment.value
        
        upstream_ref = getattr(domain_config.server_web, "upstream_ref", None)
        if upstream_ref:
            meta["upstream_ref"] = upstream_ref
        if "service_type" not in meta and domain_config.server_web.upstream:
            meta["service_type"] = domain_config.server_web.upstream.service_type.value
        if "service_type" not in meta and upstream_ref:
            meta["service_type"] = "api"

        up = domain_config.server_web.upstream
        if up:
            if "tech" not in meta:
                meta["tech"] = up.tech.value if hasattr(up.tech, "value") else up.tech
            if "tech_version" not in meta:
                meta["tech_version"] = up.tech_version
            if "tech_provider" not in meta:
                meta["tech_provider"] = up.tech_provider.value if hasattr(up.tech_provider, "value") else up.tech_provider
            if "tech_manager" not in meta:
                meta["tech_manager"] = up.tech_manager.value if hasattr(up.tech_manager, "value") else up.tech_manager
            if "tech_port" not in meta:
                meta["tech_port"] = str(up.port)
        
        if "owner" not in meta and domain_config.owner:
            meta["owner"] = domain_config.owner
        if "technical_user" not in meta and getattr(domain_config, "technical_user", None):
            meta["technical_user"] = domain_config.technical_user

        return meta
    
    def save_to_declarative(self, domain: str, meta: Dict[str, Any], server_name: Optional[str] = None) -> bool:
        """
        Guarda metadata en formato declarativo (YAML)
        
        Args:
            domain: Dominio
            meta: Metadata completa
            server_name: server_name del .conf (para inferir slug si no existe)
        
        Returns:
            True si se guardó correctamente
        """
        try:
            # Construir DomainConfig desde meta
            domain_config = self._meta_to_domain_config(domain, meta, server_name)
            if not domain_config:
                return False
            
            # Guardar
            return self.loader.save_domain(domain_config)
        except Exception as e:
            self.console.print(f"[red]❌ Error al guardar estado declarativo: {e}[/red]")
            return False
    
    def _meta_to_domain_config(self, domain: str, meta: Dict[str, Any], server_name: Optional[str] = None) -> Optional[DomainConfig]:
        """Convierte metadata a DomainConfig"""
        from .models import DomainType
        
        # Inferir tipo de dominio
        domain_type = DomainType.SUBDOMAIN if domain.count(".") >= 2 else DomainType.ROOT
        
        # Inferir slug
        slug = meta.get("slug")
        if not slug:
            domain_clean = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "")
            slug = domain_clean.split(".")[0]
        
        # Backend config
        # server_web (compat: meta puede tener "backend" o "server_web" o keys planos server_web_version)
        sw = meta.get("server_web")
        if isinstance(sw, dict):
            sw_type = (sw.get("type") or "nginx").lower()
            sw_version = sw.get("version") or meta.get("server_web_version")
            sw_mode = sw.get("mode")
        else:
            sw_type = (meta.get("backend", "nginx") or "nginx").lower()
            sw_version = meta.get("server_web_version") or meta.get("backend_version")
            sw_mode = None
        upstream_ref_val = meta.get("upstream_ref", "").strip() or None
        upstream_inline = None
        # Crear upstream con tech siempre que haya tech (api), también con upstream_ref, para persistir en YAML.
        if meta.get("service_type", "").lower() == "api" and meta.get("tech") and meta.get("tech") in ("php", "node", "python"):
            tech_provider = (meta.get("tech_provider") or "system").lower()
            tech_manager = (meta.get("tech_manager") or "npm").lower()
            port = int(meta.get("tech_port") or meta.get("node_port") or meta.get("php_port") or meta.get("python_port") or 3000)
            upstream_inline = UpstreamConfig(
                service_type=ServiceType(meta["service_type"].lower()),
                tech=TechType(meta["tech"].lower()),
                tech_version=meta.get("tech_version") or "",
                tech_provider=tech_provider,
                tech_manager=tech_manager,
                port=port,
            )
        server_web_config = ServerWebConfig(
            type=sw_type,
            version=sw_version,
            mode=sw_mode,
            upstream_ref=upstream_ref_val,
            upstream=upstream_inline,
        )

        from .catalog import resolve_provider_id
        provider_id = resolve_provider_id(self.base_dir, domain=domain, meta_provider=meta.get("provider"))
        provider_value = provider_id or meta.get("provider", "EXTERNAL")

        domain_config = DomainConfig(
            domain=domain,
            type=domain_type,
            slug=slug,
            environment=Environment(meta.get("environment", "dev").lower()),
            provider=provider_value,
            server=meta.get("server"),
            server_web=server_web_config,
            owner=meta.get("owner"),
            technical_user=meta.get("technical_user"),
            description=meta.get("description")
        )
        
        return domain_config
    
    def generate_config_from_declarative(self, domain: str) -> bool:
        """
        Genera .conf desde configuración declarativa
        
        Args:
            domain: Dominio
        
        Returns:
            True si se generó correctamente
        """
        domain_config = self.loader.get_domain(domain)
        if not domain_config:
            self.console.print(f"[yellow]⚠️ No hay configuración declarativa para {domain}[/yellow]")
            return False
        
        conf_file = self.generator.write_config(domain_config)
        return conf_file is not None
