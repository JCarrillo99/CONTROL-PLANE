"""
Gestión de Service Manifests
Almacena metadatos de sitios independientes de la configuración de Traefik
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

MANIFESTS_DIR = Path.home() / ".lsxtool" / "sites" / "manifests"


@dataclass
class ServiceManifest:
    """Manifest de servicio con metadatos completos"""
    domain: str
    provider: str  # LSX, STIC, EXTERNAL, etc.
    service_type: str  # web, api, admin, static
    backend_type: str  # apache, nginx, node, php-fpm, etc.
    backend_version: Optional[str] = None  # Versión del servidor web (Apache, Nginx)
    tech: Optional[str] = None  # Tecnología (php, node, python, etc.)
    tech_version: Optional[str] = None  # Versión de la tecnología (PHP 7.4, 8.3, Node 18, etc.)
    target: Optional[str] = None  # host:port o container:port
    path: Optional[str] = None  # Ruta en el servidor (DocumentRoot/root)
    config_path: Optional[str] = None  # Ruta del archivo de configuración (.conf)
    owner: Optional[str] = None  # Equipo responsable
    environment: str = "dev"  # dev, qa, prod
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    health_check_enabled: bool = False
    health_check_path: Optional[str] = None
    sla: Optional[Dict[str, Any]] = None  # Para futuro: uptime, response_time, etc.


def ensure_manifests_dir() -> None:
    """Asegura que el directorio de manifests existe"""
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)


def get_manifest_path(domain: str) -> Path:
    """Obtiene la ruta del archivo manifest para un dominio"""
    ensure_manifests_dir()
    # Normalizar nombre de dominio para nombre de archivo
    safe_name = domain.replace(".", "_").replace("/", "_")
    return MANIFESTS_DIR / f"{safe_name}.json"


def load_manifest(domain: str) -> Optional[ServiceManifest]:
    """
    Carga un manifest de servicio
    
    Args:
        domain: Dominio del sitio
    
    Returns:
        ServiceManifest o None si no existe
    """
    manifest_path = get_manifest_path(domain)
    
    if not manifest_path.exists():
        return None
    
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
        
        return ServiceManifest(**data)
    except Exception:
        return None


def save_manifest(manifest: ServiceManifest) -> bool:
    """
    Guarda un manifest de servicio
    
    Args:
        manifest: Manifest a guardar
    
    Returns:
        True si se guardó correctamente
    """
    ensure_manifests_dir()
    
    # Actualizar timestamps
    if not manifest.created_at:
        manifest.created_at = datetime.now().isoformat()
    manifest.updated_at = datetime.now().isoformat()
    
    manifest_path = get_manifest_path(manifest.domain)
    
    try:
        with open(manifest_path, "w") as f:
            json.dump(asdict(manifest), f, indent=2)
        return True
    except Exception:
        return False


def list_all_manifests() -> List[ServiceManifest]:
    """
    Lista todos los manifests disponibles
    
    Returns:
        Lista de ServiceManifest
    """
    ensure_manifests_dir()
    
    manifests = []
    for manifest_file in MANIFESTS_DIR.glob("*.json"):
        try:
            with open(manifest_file, "r") as f:
                data = json.load(f)
            manifests.append(ServiceManifest(**data))
        except Exception:
            continue
    
    return manifests


def delete_manifest(domain: str) -> bool:
    """
    Elimina un manifest
    
    Args:
        domain: Dominio del sitio
    
    Returns:
        True si se eliminó correctamente
    """
    manifest_path = get_manifest_path(domain)
    
    if not manifest_path.exists():
        return False
    
    try:
        manifest_path.unlink()
        return True
    except Exception:
        return False


def infer_manifest_from_traefik(
    domain: str,
    traefik_config: Dict[str, Any],
    base_dir: Path,
    config_path: Optional[Path] = None
) -> ServiceManifest:
    """
    Infiere un manifest desde configuración de Traefik
    
    Args:
        domain: Dominio del sitio
        traefik_config: Configuración de Traefik parseada
        base_dir: Directorio base del proyecto
    
    Returns:
        ServiceManifest inferido
    """
    # Extraer información del YAML de Traefik
    services = traefik_config.get("http", {}).get("services", {})
    routers = traefik_config.get("http", {}).get("routers", {})
    
    # Primero verificar si es un servicio interno de Traefik (dashboard)
    from .traefik_parser import extract_backend_from_traefik
    detected_backend_type, detected_target = extract_backend_from_traefik(traefik_config)
    
    backend_type = detected_backend_type or "unknown"
    target = detected_target
    backend_version = None  # Versión del servidor web
    tech_version = None  # Versión de la tecnología (PHP, Node, etc.)
    config_path = None
    
    # Si es servicio interno de Traefik, retornar manifest básico
    if backend_type == "TRAEFIK":
        return ServiceManifest(
            domain=domain,
            provider="LSX",  # Dashboard es siempre LSX
            service_type="admin",
            backend_type="TRAEFIK",
            backend_version=None,
            tech_version=None,
            target="internal",
            path=None,
            config_path=None,
            owner=None,
            environment="dev",
            description=f"Dashboard interno de Traefik"
        )
    
    # Inicializar variables antes de buscar routers
    service_port = None
    main_router_found = False
    
    # Buscar router que coincida exactamente con el dominio
    # Priorizar router "main" si existe, luego cualquier otro que coincida
    matched_routers = []
    
    for router_name, router_config in routers.items():
        rule = router_config.get("rule", "")
        # Verificar si el dominio está en la regla del router
        # Buscar patrones como Host(`domain`) o Host(`www.domain`)
        # El backtick puede estar escapado o no, buscar ambas variantes
        domain_patterns = [
            f"Host(`{domain}`)",
            f'Host("{domain}")',
            f"Host('{domain}')",
            f"Host(`www.{domain}`)",
            f'Host("www.{domain}")',
            f"Host('www.{domain}')",
        ]
        if any(pattern in rule for pattern in domain_patterns):
            matched_routers.append((router_name, router_config, "main" in router_name.lower()))
    
    # Ordenar: primero los que tienen "main", luego los demás
    matched_routers.sort(key=lambda x: (not x[2], x[0]))
    
    # Procesar el primer router encontrado (priorizando "main")
    for router_name, router_config, is_main in matched_routers:
        service_name = router_config.get("service")
        if service_name and service_name in services:
            service = services[service_name]
            load_balancer = service.get("loadBalancer", {})
            servers = load_balancer.get("servers", [])
            
            if servers:
                server_url = servers[0].get("url", "")
                # Extraer puerto del URL
                if ":" in server_url:
                    try:
                        port_part = server_url.split(":")[-1].rstrip("/")
                        service_port = port_part
                    except:
                        pass
                
                # Inferir backend_type desde el nombre del servicio o puerto estándar
                if "apache" in service_name.lower() or "9200" in server_url:
                    backend_type = "apache"
                elif "nginx" in service_name.lower() or "9100" in server_url:
                    backend_type = "nginx"
                
                # Obtener puerto estándar desde catálogo
                if backend_type:
                    from .catalogs import get_backend_port
                    standard_port = get_backend_port(backend_type)
                    if standard_port:
                        target = f"localhost:{standard_port}"
                    else:
                        # Fallback: extraer de URL
                        target = server_url.replace("http://", "").replace("https://", "")
                else:
                    # Extraer de URL si no se pudo inferir backend
                    target = server_url.replace("http://", "").replace("https://", "")
                main_router_found = True
                break
    
    # Si no se encontró ningún router que coincida exactamente, buscar por dominio en string (fallback)
    if not main_router_found:
        for router_name, router_config in routers.items():
            if domain in str(router_config):
                service_name = router_config.get("service")
                if service_name and service_name in services:
                    service = services[service_name]
                    load_balancer = service.get("loadBalancer", {})
                    servers = load_balancer.get("servers", [])
                    
                    if servers:
                        server_url = servers[0].get("url", "")
                        # Extraer puerto del URL
                        if ":" in server_url:
                            try:
                                port_part = server_url.split(":")[-1].rstrip("/")
                                service_port = port_part
                            except:
                                pass
                        
                        # Inferir backend_type desde el nombre del servicio o puerto estándar
                        if "apache" in service_name.lower() or "9200" in server_url:
                            backend_type = "apache"
                        elif "nginx" in service_name.lower() or "9100" in server_url:
                            backend_type = "nginx"
                        
                        # Obtener puerto estándar desde catálogo
                        if backend_type:
                            from .catalogs import get_backend_port
                            standard_port = get_backend_port(backend_type)
                            if standard_port:
                                target = f"localhost:{standard_port}"
                            else:
                                # Fallback: extraer de URL
                                target = server_url.replace("http://", "").replace("https://", "")
                        else:
                            # Extraer de URL si no se pudo inferir backend
                            target = server_url.replace("http://", "").replace("https://", "")
                        break
    
    # Intentar leer metadatos desde comentarios estructurados primero
    # SOLO si config_path es un Path y el nombre del archivo coincide exactamente con el dominio
    meta_from_conf = None
    if config_path:
        try:
            config_path_obj = Path(config_path) if isinstance(config_path, str) else config_path
            # Verificar que el nombre del archivo sea exactamente {domain}.conf
            if config_path_obj.exists() and config_path_obj.name == f"{domain}.conf":
                from .meta_parser import parse_meta_from_conf
                meta_from_conf = parse_meta_from_conf(config_path_obj)
        except Exception:
            pass
    
    # Intentar inferir desde archivos de configuración
    path = None
    
    # Buscar en Apache (múltiples ubicaciones posibles)
    apache_paths = [
        base_dir / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
        base_dir / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
        base_dir / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf",
    ]
    
    # También buscar recursivamente en subdirectorios si existe
    apache_base = base_dir / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available"
    if apache_base.exists():
        for conf_file in apache_base.rglob(f"{domain}.conf"):
            # Verificar que el nombre del archivo sea exactamente {domain}.conf
            if conf_file.exists() and conf_file.name == f"{domain}.conf" and conf_file not in apache_paths:
                apache_paths.insert(0, conf_file)
    
    for apache_config_path in apache_paths:
        if apache_config_path.exists():
            # Verificar que el nombre del archivo sea exactamente {domain}.conf
            if apache_config_path.name != f"{domain}.conf":
                continue
            # Guardar referencia al archivo de configuración encontrado
            if not config_path:
                config_path = str(apache_config_path)
            
            # Intentar leer metadatos desde comentarios SOLO si es el archivo exacto
            if not meta_from_conf:
                try:
                    from .meta_parser import parse_meta_from_conf
                    meta_from_conf = parse_meta_from_conf(apache_config_path)
                except Exception:
                    pass
            
            try:
                content = apache_config_path.read_text()
                
                # Extraer DocumentRoot
                if "DocumentRoot" in content:
                    for line in content.split("\n"):
                        line_stripped = line.strip()
                        if "DocumentRoot" in line_stripped and not line_stripped.startswith("#"):
                            parts = line_stripped.split("DocumentRoot", 1)
                            if len(parts) > 1:
                                path_candidate = parts[1].strip()
                                if "#" in path_candidate:
                                    path_candidate = path_candidate.split("#")[0].strip()
                                path = path_candidate.split()[0] if path_candidate.split() else None
                                if path:
                                    break
                
                # Extraer versión de PHP desde PHP-FPM socket (es tech_version, no backend_version)
                if tech_version is None and "php" in content.lower():
                    for line in content.split("\n"):
                        line_lower = line.lower()
                        if "php" in line_lower and "fpm.sock" in line_lower:
                            # Buscar patrones como php8.3-fpm.sock, php7.2-fpm.sock
                            import re
                            php_match = re.search(r'php(\d+\.\d+)-fpm', line_lower)
                            if php_match:
                                tech_version = f"PHP {php_match.group(1)}"
                                break
                
                if path:
                    break
            except Exception as e:
                continue
    
    # Buscar en Nginx si no se encontró en Apache
    if not path or not config_path:
        nginx_paths = [
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            base_dir / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            base_dir / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf",
            # Buscar también en lunarsystemx
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "lunarsystemx" / f"{domain}.conf",
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "lunarsystemx" / "dev" / f"{domain}.conf",
            base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "lunarsystemx" / "prod" / f"{domain}.conf",
        ]
        
        # También buscar recursivamente SOLO archivos con nombre exacto del dominio
        nginx_base = base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx"
        if nginx_base.exists():
            # Buscar SOLO archivos con el nombre exacto {domain}.conf (no subdominios)
            for conf_file in nginx_base.rglob(f"{domain}.conf"):
                # Verificar que el nombre del archivo sea exactamente {domain}.conf
                if conf_file.exists() and conf_file.name == f"{domain}.conf" and conf_file not in nginx_paths:
                    nginx_paths.insert(0, conf_file)
        
        for nginx_config_path in nginx_paths:
            if nginx_config_path.exists():
                # Verificar que el nombre del archivo sea exactamente {domain}.conf
                if nginx_config_path.name != f"{domain}.conf":
                    continue
                # Establecer config_path si no se ha establecido aún
                if not config_path:
                    config_path = str(nginx_config_path)
                # Intentar leer metadatos desde comentarios SOLO si es el archivo exacto
                if not meta_from_conf:
                    try:
                        from .meta_parser import parse_meta_from_conf
                        meta_from_conf = parse_meta_from_conf(nginx_config_path)
                    except Exception:
                        pass
                
                try:
                    content = nginx_config_path.read_text()
                    if "root" in content:
                        for line in content.split("\n"):
                            line_stripped = line.strip()
                            if "root" in line_stripped and not line_stripped.startswith("#"):
                                parts = line_stripped.split("root", 1)
                                if len(parts) > 1:
                                    path_candidate = parts[1].strip().rstrip(";").strip()
                                    if "#" in path_candidate:
                                        path_candidate = path_candidate.split("#")[0].strip()
                                    path = path_candidate.split()[0] if path_candidate.split() else None
                                    if path:
                                        break
                    
                    # Extraer versión de PHP desde PHP-FPM socket (es tech_version, no backend_version)
                    if tech_version is None and "php" in content.lower():
                        for line in content.split("\n"):
                            line_lower = line.lower()
                            if "php" in line_lower and "fpm.sock" in line_lower:
                                import re
                                php_match = re.search(r'php(\d+\.\d+)-fpm', line_lower)
                                if php_match:
                                    tech_version = f"PHP {php_match.group(1)}"
                                    break
                    
                    if path:
                        break
                except Exception:
                    continue
        
        # NO buscar por puerto - solo archivos con nombre exacto del dominio
    
    # Inferir provider desde dominio
    provider = "EXTERNAL"
    if "yucatan.gob.mx" in domain:
        provider = "STIC"
    elif "lunarsystemx.com" in domain:
        provider = "LSX"
    
    # Inferir environment
    environment = "dev"
    if domain.startswith("qa-") or "qa" in domain:
        environment = "qa"
    elif not domain.startswith("dev-"):
        environment = "prod"
    
    # Inferir service_type
    service_type = "web"
    if "api" in domain:
        service_type = "api"
    elif "admin" in domain:
        service_type = "admin"
    
    # Si hay metadatos desde comentarios, usarlos (tienen prioridad)
    if meta_from_conf:
        from .meta_parser import meta_to_manifest_dict
        meta_dict = meta_to_manifest_dict(meta_from_conf, domain)
        # Combinar con valores inferidos (los metadatos tienen prioridad)
        return ServiceManifest(
            domain=domain,
            provider=meta_dict.get("provider", provider),
            service_type=meta_dict.get("service_type", service_type),
            backend_type=meta_dict.get("backend_type", backend_type),
            backend_version=meta_dict.get("backend_version") or backend_version,
            tech=meta_dict.get("tech"),  # Tecnología desde metadata
            tech_version=meta_dict.get("tech_version") or tech_version,  # Versión desde metadata o inferida
            target=target,
            path=path,
            config_path=config_path,
            owner=meta_dict.get("owner"),  # Sin valor por defecto
            environment=meta_dict.get("environment", environment),
            description=meta_dict.get("description", f"Sitio {domain}"),
            tags=None
        )
    
    # Si no hay metadatos, usar valores inferidos
    return ServiceManifest(
        domain=domain,
        provider=provider,
        service_type=service_type,
        backend_type=backend_type,
        backend_version=backend_version,  # Versión del servidor web
        tech_version=tech_version,  # Versión de la tecnología
        target=target,
        path=path,
        config_path=config_path,
        owner=None,  # Sin valor por defecto
        environment=environment,
        description=f"Sitio {domain}",
        tags=None
    )
