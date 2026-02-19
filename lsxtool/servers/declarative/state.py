"""
State Engine: Compara estado deseado (YAML) vs estado real (.conf)
Permite detectar drift y reconciliar
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .models import DomainConfig
from .loader import DeclarativeLoader
from ..nginx.parser import parse_nginx_config, NginxConfig


class StateDiff:
    """Representa una diferencia entre estado deseado y real"""
    def __init__(self, domain: str, field: str, desired: Any, actual: Any, severity: str = "warning"):
        self.domain = domain
        self.field = field
        self.desired = desired
        self.actual = actual
        self.severity = severity  # "error", "warning", "info"


class StateEngine:
    """Motor de estado: compara deseado vs real"""
    
    def __init__(self, base_dir: Path, console: Optional[Console] = None):
        self.base_dir = base_dir
        self.console = console or Console()
        self.loader = DeclarativeLoader(base_dir, console)
    
    def detect_drift(self, domain: Optional[str] = None) -> List[StateDiff]:
        """
        Detecta drift entre estado deseado (YAML) y real (.conf)
        
        Args:
            domain: Si se especifica, solo detecta drift para ese dominio
        
        Returns:
            Lista de StateDiff
        """
        if not self.loader.load_all():
            return []
        
        diffs = []
        
        # Si se especifica un dominio, solo verificar ese
        domains_to_check = [domain] if domain else list(self.loader._domains.keys())
        
        for domain_name in domains_to_check:
            domain_config = self.loader.get_domain(domain_name)
            if not domain_config:
                continue
            
            # Buscar .conf real
            from ..nginx.parser import find_nginx_configs
            config_files = find_nginx_configs(self.base_dir)
            conf_file = None
            for cf in config_files:
                if domain_name == cf.stem or domain_name in cf.stem:
                    conf_file = cf
                    break
            
            if not conf_file:
                # .conf no existe pero debería existir según YAML
                diffs.append(StateDiff(
                    domain_name,
                    "config_file",
                    "exists",
                    "missing",
                    "error"
                ))
                continue
            
            # Parsear .conf
            nginx_config = parse_nginx_config(conf_file)
            if not nginx_config:
                diffs.append(StateDiff(
                    domain_name,
                    "config_file",
                    "valid",
                    "invalid",
                    "error"
                ))
                continue
            
            # Comparar campos
            diffs.extend(self._compare_domain_config(domain_config, nginx_config, domain_name))
        
        return diffs
    
    def _compare_domain_config(self, desired: DomainConfig, actual: NginxConfig, domain: str) -> List[StateDiff]:
        """Compara configuración deseada vs real"""
        diffs = []
        
        # Comparar server_web type (compat: .conf META puede tener "backend" o "server_web")
        desired_sw = desired.server_web.type.value if desired.server_web and desired.server_web.type else ""
        actual_sw = (actual.meta.get("server_web") or actual.meta.get("backend") or "").lower()
        if desired_sw != actual_sw:
            diffs.append(StateDiff(
                domain, "server_web", desired_sw, actual_sw, "error"
            ))
        
        # Comparar environment
        desired_env = desired.environment.value
        actual_env = actual.meta.get("environment", "").lower()
        if desired_env != actual_env:
            diffs.append(StateDiff(
                domain, "environment", desired_env, actual_env, "warning"
            ))
        
        # Comparar provider
        desired_provider = desired.provider
        actual_provider = actual.meta.get("provider", "")
        if desired_provider != actual_provider:
            diffs.append(StateDiff(
                domain, "provider", desired_provider, actual_provider, "warning"
            ))
        
        # Comparar tech metadata (si existe upstream)
        if desired.server_web and desired.server_web.upstream:
            upstream = desired.server_web.upstream
            actual_tech = actual.meta.get("tech", "").lower()
            if upstream.tech.value != actual_tech:
                diffs.append(StateDiff(
                    domain, "tech", upstream.tech.value, actual_tech, "error"
                ))
            
            actual_tech_version = actual.meta.get("tech_version", "")
            if upstream.tech_version != actual_tech_version:
                diffs.append(StateDiff(
                    domain, "tech_version", upstream.tech_version, actual_tech_version, "warning"
                ))
            
            actual_tech_provider = actual.meta.get("tech_provider", "").lower()
            if upstream.tech_provider != actual_tech_provider:
                diffs.append(StateDiff(
                    domain, "tech_provider", upstream.tech_provider, actual_tech_provider, "error"
                ))
            
            actual_tech_manager = actual.meta.get("tech_manager", "").lower()
            if upstream.tech_manager != actual_tech_manager:
                diffs.append(StateDiff(
                    domain, "tech_manager", upstream.tech_manager, actual_tech_manager, "error"
                ))
        
        return diffs
    
    def display_drift(self, diffs: List[StateDiff]):
        """Muestra drift en formato legible"""
        if not diffs:
            self.console.print("[green]✅ No se detectó drift. Estado deseado y real coinciden.[/green]")
            return
        
        # Agrupar por dominio
        by_domain: Dict[str, List[StateDiff]] = {}
        for diff in diffs:
            if diff.domain not in by_domain:
                by_domain[diff.domain] = []
            by_domain[diff.domain].append(diff)
        
        for domain, domain_diffs in by_domain.items():
            table = Table(title=f"Drift detectado: {domain}", show_header=True, header_style="bold")
            table.add_column("Campo", style="cyan")
            table.add_column("Deseado", style="green")
            table.add_column("Real", style="yellow")
            table.add_column("Severidad", style="red")
            
            for diff in domain_diffs:
                severity_style = {
                    "error": "[red]ERROR[/red]",
                    "warning": "[yellow]WARNING[/yellow]",
                    "info": "[blue]INFO[/blue]"
                }.get(diff.severity, diff.severity)
                
                table.add_row(
                    diff.field,
                    str(diff.desired),
                    str(diff.actual),
                    severity_style
                )
            
            self.console.print(table)
            self.console.print()
