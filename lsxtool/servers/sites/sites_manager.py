"""
Gestor de sitios - Integra Traefik y Service Manifests
Proporciona vistas operativas y enterprise de los sitios
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

try:
    from .traefik_parser import list_traefik_sites, parse_traefik_config
    from .manifest import (
        load_manifest,
        list_all_manifests,
        ServiceManifest,
        infer_manifest_from_traefik,
        save_manifest
    )
except ImportError:
    # Fallback para imports absolutos cuando se ejecuta desde diferentes contextos
    import sys
    from pathlib import Path as PathLib
    current_dir = PathLib(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir.parent.parent.parent))
    from servers.sites.traefik_parser import list_traefik_sites, parse_traefik_config
    from servers.sites.manifest import (
        load_manifest,
        list_all_manifests,
        ServiceManifest,
        infer_manifest_from_traefik,
        save_manifest
    )


class SiteInfo:
    """Información completa de un sitio"""
    
    def __init__(
        self,
        domain: str,
        manifest: Optional[ServiceManifest] = None,
        traefik_data: Optional[Dict[str, Any]] = None
    ):
        self.domain = domain
        self.manifest = manifest
        self.traefik_data = traefik_data
        
        # Si no hay manifest, crear uno básico desde Traefik
        if not self.manifest and self.traefik_data:
            self.manifest = infer_manifest_from_traefik(
                domain,
                self.traefik_data,
                Path(__file__).parent.parent.parent.parent
            )
    
    @property
    def provider(self) -> str:
        """Proveedor del servicio"""
        return self.manifest.provider if self.manifest else "UNKNOWN"
    
    @property
    def backend_type(self) -> str:
        """Tipo de backend"""
        return self.manifest.backend_type if self.manifest else "unknown"
    
    @property
    def backend_version(self) -> str:
        """Versión del servidor web (Apache, Nginx)"""
        return self.manifest.backend_version or "N/A"
    
    @property
    def tech_version(self) -> str:
        """Versión de la tecnología (PHP, Node, etc.)"""
        return self.manifest.tech_version or "N/A"
    
    @property
    def target(self) -> str:
        """Target del backend"""
        return self.manifest.target or "N/A"
    
    @property
    def path(self) -> str:
        """Ruta en el servidor"""
        return self.manifest.path or "N/A"
    
    @property
    def config_path(self) -> str:
        """Ruta del archivo de configuración (.conf)"""
        # Solo retornar si es un archivo .conf, no .yml de Traefik
        # Y verificar que el nombre del archivo sea exactamente {domain}.conf
        if self.manifest and self.manifest.config_path:
            config_path_str = self.manifest.config_path
            if config_path_str.endswith('.conf'):
                # Verificar que el nombre del archivo sea exactamente el dominio
                try:
                    from pathlib import Path
                    config_path_obj = Path(config_path_str)
                    # Si es relativo, intentar resolverlo
                    if not config_path_obj.is_absolute():
                        # Intentar desde diferentes bases
                        possible_bases = [
                            Path(__file__).parent.parent.parent.parent,
                            Path(__file__).parent.parent.parent.parent.parent,
                        ]
                        for base in possible_bases:
                            full_path = base / config_path_obj
                            if full_path.exists():
                                config_path_obj = full_path
                                break
                    
                    # Verificar que el nombre del archivo sea exactamente {domain}.conf
                    if config_path_obj.exists() and config_path_obj.name == f"{self.domain}.conf":
                        return config_path_str
                    # Si el nombre no coincide exactamente, no retornarlo
                except:
                    pass
        return "N/A"
    
    @property
    def traefik_path(self) -> str:
        """Ruta del archivo de configuración de Traefik"""
        if self.traefik_data:
            # Intentar obtener la ruta del archivo Traefik desde el contexto
            # Por ahora retornar N/A, se establecerá en get_site_info
            return getattr(self, '_traefik_file_path', "N/A")
        return "N/A"
    
    @property
    def owner(self) -> str:
        """Dueño del servicio"""
        return self.manifest.owner or "No configurado"
    
    @property
    def environment(self) -> str:
        """Ambiente"""
        return self.manifest.environment if self.manifest else "dev"
    
    @property
    def service_type(self) -> str:
        """Tipo de servicio"""
        return self.manifest.service_type if self.manifest else "web"


def load_all_sites(base_dir: Path, console: Optional[Console] = None) -> List[SiteInfo]:
    """
    Carga todos los sitios desde Traefik y los cruza con manifests
    
    Args:
        base_dir: Directorio base del proyecto (servers-install/)
        console: Console de Rich para salida
    
    Returns:
        Lista de SiteInfo
    """
    # base_dir debe ser servers-install/ (directorio raíz del proyecto)
    # Las configuraciones de Traefik están en lsxtool/servers/traefik/
    # pero también pueden estar en servers-install/traefik/ (estructura original)
    
    # Opción 1: Estructura nueva (lsxtool/servers/traefik/)
    if (base_dir / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http").exists():
        traefik_config_dir = base_dir / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http"
    # Opción 2: Estructura original (servers-install/traefik/)
    elif (base_dir / "traefik" / "config" / "dynamic" / "http").exists():
        traefik_config_dir = base_dir / "traefik" / "config" / "dynamic" / "http"
    # Opción 3: Si base_dir es lsxtool/servers/, subir dos niveles
    elif (base_dir.parent.parent / "traefik" / "config" / "dynamic" / "http").exists():
        traefik_config_dir = base_dir.parent.parent / "traefik" / "config" / "dynamic" / "http"
    else:
        # Fallback: buscar desde el archivo actual
        current = Path(__file__).parent.parent.parent.parent.resolve()
        if (current / "traefik" / "config" / "dynamic" / "http").exists():
            traefik_config_dir = current / "traefik" / "config" / "dynamic" / "http"
        else:
            traefik_config_dir = current / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http"
    
    # Obtener sitios de Traefik
    traefik_sites = list_traefik_sites(traefik_config_dir, console)
    
    # Cargar manifests existentes
    manifests_by_domain = {m.domain: m for m in list_all_manifests()}
    
    sites = []
    
    for traefik_site in traefik_sites:
        domain = traefik_site["domain"]
        
        # Cargar configuración de Traefik
        traefik_file = Path(traefik_site["traefik_path"])
        traefik_config = parse_traefik_config(traefik_file)
        
        # Obtener manifest (existente o inferido)
        manifest = manifests_by_domain.get(domain)
        
        # Si no existe manifest, inferirlo y guardarlo
        if not manifest and traefik_config:
            manifest = infer_manifest_from_traefik(domain, traefik_config, base_dir)
            # Guardar manifest inferido para futuras referencias
            if manifest:
                save_manifest(manifest)
        
        sites.append(SiteInfo(
            domain=domain,
            manifest=manifest,
            traefik_data=traefik_config
        ))
    
    return sites


def get_site_info(domain: str, base_dir: Path, console: Optional[Console] = None) -> Optional[SiteInfo]:
    """
    Obtiene información detallada de un sitio específico
    
    Args:
        domain: Dominio del sitio
        base_dir: Directorio base del proyecto (servers-install/)
        console: Console de Rich para salida
    
    Returns:
        SiteInfo o None si no se encuentra
    """
    # Resolver directorio de Traefik de forma flexible
    # Opción 1: Estructura nueva (lsxtool/servers/traefik/)
    if (base_dir / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http").exists():
        traefik_config_dir = base_dir / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http"
    # Opción 2: Estructura original (servers-install/traefik/)
    elif (base_dir / "traefik" / "config" / "dynamic" / "http").exists():
        traefik_config_dir = base_dir / "traefik" / "config" / "dynamic" / "http"
    # Opción 3: Si base_dir es lsxtool/servers/, subir dos niveles
    elif (base_dir.parent.parent / "traefik" / "config" / "dynamic" / "http").exists():
        traefik_config_dir = base_dir.parent.parent / "traefik" / "config" / "dynamic" / "http"
    else:
        # Fallback: buscar desde el archivo actual
        current = Path(__file__).parent.parent.parent.parent.resolve()
        if (current / "traefik" / "config" / "dynamic" / "http").exists():
            traefik_config_dir = current / "traefik" / "config" / "dynamic" / "http"
        else:
            traefik_config_dir = current / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http"
    
    # Buscar archivo de Traefik para este dominio
    traefik_file = traefik_config_dir / f"{domain}.yml"
    
    if not traefik_file.exists():
        # Buscar en otros archivos que puedan contener múltiples dominios
        for yaml_file in traefik_config_dir.glob("*.yml"):
            config_data = parse_traefik_config(yaml_file)
            if config_data:
                extracted_domain = extract_domain_from_traefik(config_data)
                if extracted_domain == domain:
                    traefik_file = yaml_file
                    break
    
    # Guardar referencia al archivo de Traefik como config_path si no se encuentra otro
    traefik_config_path = None
    if traefik_file.exists():
        traefik_config_path = str(traefik_file.relative_to(base_dir)) if base_dir in traefik_file.parents else str(traefik_file)
    
    traefik_config = parse_traefik_config(traefik_file) if traefik_file.exists() else None
    
    # Cargar manifest
    manifest = load_manifest(domain)
    
    # Validar manifest cargado: verificar que config_path sea válido (nombre exacto del dominio)
    if manifest and manifest.config_path:
        try:
            config_path_obj = Path(manifest.config_path)
            if not config_path_obj.is_absolute():
                config_path_obj = base_dir / config_path_obj
            
            # Si el archivo no existe o el nombre no coincide exactamente, limpiar config_path
            if not config_path_obj.exists() or config_path_obj.name != f"{domain}.conf":
                manifest.config_path = None
                # Si el owner viene de un archivo incorrecto, también limpiarlo
                # (solo si config_path estaba establecido, significa que venía de ahí)
                if manifest.owner:
                    manifest.owner = None
                save_manifest(manifest)
        except:
            # Si hay error validando, limpiar config_path
            manifest.config_path = None
            if manifest.owner:
                manifest.owner = None
            save_manifest(manifest)
    
    # Si no existe, inferirlo
    if not manifest and traefik_config:
        manifest = infer_manifest_from_traefik(domain, traefik_config, base_dir, config_path=None)
        if manifest:
            save_manifest(manifest)
    
    if not traefik_config and not manifest:
        return None
    
    # Crear SiteInfo
    site_info = SiteInfo(
        domain=domain,
        manifest=manifest,
        traefik_data=traefik_config
    )
    
    # Establecer ruta de Traefik como atributo temporal
    if traefik_config_path:
        site_info._traefik_file_path = traefik_config_path
    
    # Si no hay config_path (.conf), intentar buscarlo o crearlo
    if site_info.config_path == "N/A" and manifest:
        # Buscar archivo .conf basado en backend y dominio
        conf_path = _find_or_create_conf_file(domain, manifest.backend_type, manifest.target, base_dir)
        if conf_path:
            manifest.config_path = str(conf_path.relative_to(base_dir)) if base_dir in conf_path.parents else str(conf_path)
            save_manifest(manifest)
    
    return site_info


def _find_or_create_conf_file(domain: str, backend_type: str, target: Optional[str], base_dir: Path) -> Optional[Path]:
    """
    Busca o crea archivo de configuración .conf para un dominio
    
    Args:
        domain: Dominio del sitio
        backend_type: Tipo de backend (nginx, apache)
        target: Target del backend (ej: localhost:9100 para Nginx, localhost:9200 para Apache)
        base_dir: Directorio base del proyecto
    
    Returns:
        Path del archivo .conf encontrado o creado, o None
    """
    from pathlib import Path
    
    backend_lower = backend_type.lower()
    
    # Determinar ambiente y proveedor
    environment = "dev"
    if domain.startswith("qa-") or "qa" in domain:
        environment = "qa"
    elif not domain.startswith("dev-"):
        environment = "prod"
    
    provider = "stic"
    if "lunarsystemx.com" in domain:
        provider = "lunarsystemx"
    elif "yucatan.gob.mx" in domain:
        provider = "stic"
    
    # Buscar archivo existente
    if backend_lower == "nginx":
        search_paths = [
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / provider / environment / f"{domain}.conf",
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / provider / f"{domain}.conf",
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / f"{domain}.conf",
        ]
        
        # Buscar recursivamente SOLO archivos con nombre exacto
        nginx_base = base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx"
        if nginx_base.exists():
            for conf_file in nginx_base.rglob(f"{domain}.conf"):
                # Verificar que el nombre del archivo sea exactamente {domain}.conf
                if conf_file.exists() and conf_file.name == f"{domain}.conf":
                    return conf_file
        
        # Si no existe, crear estructura básica
        # Por ahora solo retornar None para no crear archivos automáticamente
        # El usuario puede crearlo manualmente con `lsxtool servers sites meta`
        return None
        
    elif backend_lower == "apache":
        search_paths = [
            base_dir / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / environment / f"{domain}.conf",
            base_dir / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / f"{domain}.conf",
        ]
        
        apache_base = base_dir / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available"
        if apache_base.exists():
            for conf_file in apache_base.rglob(f"{domain}.conf"):
                # Verificar que el nombre del archivo sea exactamente {domain}.conf
                if conf_file.exists() and conf_file.name == f"{domain}.conf":
                    return conf_file
        
        return None
    
    return None


def extract_domain_from_traefik(config_data: Dict[str, Any]) -> Optional[str]:
    """Extrae dominio de configuración de Traefik"""
    routers = config_data.get("http", {}).get("routers", {})
    
    for router_name, router_config in routers.items():
        rule = router_config.get("rule", "")
        if "Host(`" in rule:
            domain = rule.split("Host(`")[1].split("`)")[0]
            return domain
    
    return None
