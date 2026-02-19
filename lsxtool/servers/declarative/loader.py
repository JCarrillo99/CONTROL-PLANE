"""
Loader y parser del sistema declarativo
Carga YAML y los convierte a modelos Pydantic
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, List, Any
from rich.console import Console

from .models import (
    RootOrchestrator,
    DomainConfig,
    ProviderConfig,
    ServerConfig,
    ServiceConfig,
    GlobalsConfig
)
from . import get_declarative_root, chown_to_project_owner
from .catalog import resolve_provider_id
from .upstream_convention import site_path, sites_dir


def _normalize_domain_data(data: dict) -> dict:
    """Compatibilidad: YAML con 'backend:' se mapea a 'server_web:'."""
    if "backend" in data and "server_web" not in data:
        data = {**data, "server_web": data["backend"]}
    return data


class DeclarativeLoader:
    """Carga y gestiona el estado declarativo"""
    
    def __init__(self, base_dir: Path, console: Optional[Console] = None):
        self.base_dir = base_dir
        self.console = console or Console()
        self.declarative_root = get_declarative_root(base_dir)
        
        # Cache de configuraciones cargadas
        self._root: Optional[RootOrchestrator] = None
        self._globals: Optional[GlobalsConfig] = None
        self._providers: Dict[str, ProviderConfig] = {}
        self._servers: Dict[str, ServerConfig] = {}
        self._domains: Dict[str, DomainConfig] = {}
        self._services: Dict[str, ServiceConfig] = {}
    
    def load_root(self) -> Optional[RootOrchestrator]:
        """Carga el orquestador raíz (lsx.yaml)"""
        root_file = self.declarative_root / "lsx.yaml"
        
        if not root_file.exists():
            return None
        
        try:
            with open(root_file, "r") as f:
                data = yaml.safe_load(f) or {}
            self._root = RootOrchestrator(**data)
            return self._root
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al cargar lsx.yaml: {e}[/red]")
            return None
    
    def load_globals(self) -> Optional[GlobalsConfig]:
        """Carga globals.yaml"""
        globals_file = self.declarative_root / "globals.yaml"
        
        if not globals_file.exists():
            return None
        
        try:
            with open(globals_file, "r") as f:
                data = yaml.safe_load(f) or {}
            self._globals = GlobalsConfig(**data)
            return self._globals
        except Exception as e:
            if self.console:
                self.console.print(f"[yellow]⚠️ Error al cargar globals.yaml: {e}[/yellow]")
            return None
    
    def load_all(self) -> bool:
        """Carga todo el estado declarativo. Domains desde sites canónicos (providers/.../sites/) y/o legacy (root.domains, domains/)."""
        root = self.load_root()
        self.load_globals()
        if root:
            for provider_path in root.providers:
                self._load_provider(provider_path)
            for server_path in root.servers:
                self._load_server(server_path)
            for domain_path in root.domains:
                self._load_domain(domain_path)
            for service_path in root.services:
                self._load_service(service_path)
        self._load_domains_from_sites()
        self._load_domains_legacy()
        return True

    def _load_domains_legacy(self):
        """Carga domains desde legacy .lsxtool/domains/*.yaml (no pisa si ya se cargó desde sites)."""
        legacy_dir = self.declarative_root / "domains"
        if not legacy_dir.exists():
            return
        for f in legacy_dir.glob("*.yaml"):
            if f.stem in self._domains:
                continue
            try:
                with open(f, "r") as fp:
                    data = yaml.safe_load(fp) or {}
                data = _normalize_domain_data(data)
                domain = DomainConfig(**data)
                self._domains[domain.domain] = domain
            except Exception:
                pass

    def _load_domains_from_sites(self):
        """Carga domains desde estructura canónica: providers/<id>/environments/<env>/servers/<server>/sites/*.yaml"""
        root = self.declarative_root / "providers"
        if not root.exists():
            return
        for provider_dir in root.iterdir():
            if not provider_dir.is_dir():
                continue
            envs = provider_dir / "environments"
            if not envs.exists():
                continue
            for env_dir in envs.iterdir():
                if not env_dir.is_dir():
                    continue
                servers_dir = env_dir / "servers"
                if not servers_dir.exists():
                    continue
                for server_dir in servers_dir.iterdir():
                    if not server_dir.is_dir():
                        continue
                    sites = server_dir / "sites"
                    if not sites.exists():
                        continue
                    for site_file in sites.glob("*.yaml"):
                        try:
                            with open(site_file, "r") as f:
                                data = yaml.safe_load(f) or {}
                            data = _normalize_domain_data(data)
                            domain = DomainConfig(**data)
                            self._domains[domain.domain] = domain
                        except Exception:
                            pass
    
    def _load_provider(self, relative_path: str):
        """Carga un archivo de provider"""
        provider_file = self.declarative_root / relative_path
        if not provider_file.exists():
            if self.console:
                self.console.print(f"[yellow]⚠️ Provider no encontrado: {relative_path}[/yellow]")
            return
        
        try:
            with open(provider_file, "r") as f:
                data = yaml.safe_load(f) or {}
            provider = ProviderConfig(**data)
            self._providers[provider.name] = provider
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al cargar provider {relative_path}: {e}[/red]")
    
    def _load_server(self, relative_path: str):
        """Carga un archivo de server"""
        server_file = self.declarative_root / relative_path
        if not server_file.exists():
            if self.console:
                self.console.print(f"[yellow]⚠️ Server no encontrado: {relative_path}[/yellow]")
            return
        
        try:
            with open(server_file, "r") as f:
                data = yaml.safe_load(f) or {}
            server = ServerConfig(**data)
            self._servers[server.name] = server
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al cargar server {relative_path}: {e}[/red]")
    
    def _load_domain(self, relative_path: str):
        """Carga un archivo de domain"""
        domain_file = self.declarative_root / relative_path
        if not domain_file.exists():
            if self.console:
                self.console.print(f"[yellow]⚠️ Domain no encontrado: {relative_path}[/yellow]")
            return
        
        try:
            with open(domain_file, "r") as f:
                data = yaml.safe_load(f) or {}
            data = _normalize_domain_data(data)
            domain = DomainConfig(**data)
            self._domains[domain.domain] = domain
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al cargar domain {relative_path}: {e}[/red]")
    
    def _load_service(self, relative_path: str):
        """Carga un archivo de service"""
        service_file = self.declarative_root / relative_path
        if not service_file.exists():
            if self.console:
                self.console.print(f"[yellow]⚠️ Service no encontrado: {relative_path}[/yellow]")
            return
        
        try:
            with open(service_file, "r") as f:
                data = yaml.safe_load(f) or {}
            service = ServiceConfig(**data)
            self._services[service.name] = service
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al cargar service {relative_path}: {e}[/red]")
    
    def get_domain(self, domain: str) -> Optional[DomainConfig]:
        """Obtiene la configuración de un dominio"""
        return self._domains.get(domain)
    
    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Obtiene la configuración de un provider"""
        return self._providers.get(name)
    
    def get_server(self, name: str) -> Optional[ServerConfig]:
        """Obtiene la configuración de un servidor"""
        return self._servers.get(name)
    
    def get_service(self, name: str) -> Optional[ServiceConfig]:
        """Obtiene la configuración de un servicio"""
        return self._services.get(name)
    
    def get_defaults(self) -> Dict[str, Any]:
        """Obtiene defaults combinados (globals + root)"""
        defaults = {}
        if self._globals and self._globals.defaults:
            defaults.update(self._globals.defaults)
        if self._root and self._root.defaults:
            defaults.update(self._root.defaults)
        return defaults
    
    def save_domain(self, domain: DomainConfig) -> bool:
        """Guarda la configuración de un dominio (site) en estructura canónica: providers/<id>/environments/<env>/servers/<server>/sites/<domain>.yaml"""
        provider_id = resolve_provider_id(self.base_dir, domain=domain.domain, meta_provider=domain.provider)
        if not provider_id:
            provider_id = (domain.provider or "").strip().lower()
        env = getattr(domain.environment, "value", None) or str(domain.environment) if domain.environment else "dev"
        server = (domain.server_web.type or "nginx").lower() if domain.server_web and domain.server_web.type else "nginx"
        if hasattr(server, "value"):
            server = server.value
        domain_file = site_path(self.base_dir, provider_id, env, server, domain.domain)
        try:
            domain_file.parent.mkdir(parents=True, exist_ok=True)
            chown_to_project_owner(domain_file.parent, self.base_dir)
            with open(domain_file, "w") as f:
                dump_fn = getattr(domain, "model_dump", None) or getattr(domain, "dict")
                payload = dump_fn(by_alias=True, exclude_none=True)
                yaml.dump(payload, f, default_flow_style=False, sort_keys=False)
            chown_to_project_owner(domain_file, self.base_dir)
            self._domains[domain.domain] = domain
            return True
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al guardar domain: {e}[/red]")
            return False
    
    def _save_root(self):
        """Guarda el orquestador raíz"""
        root_file = self.declarative_root / "lsx.yaml"
        try:
            with open(root_file, "w") as f:
                yaml.dump(self._root.dict(exclude_none=True), f, default_flow_style=False, sort_keys=False)
            chown_to_project_owner(root_file, self.base_dir)
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al guardar lsx.yaml: {e}[/red]")
