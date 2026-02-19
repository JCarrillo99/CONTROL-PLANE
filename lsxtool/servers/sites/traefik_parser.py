"""
Parser de configuraciones de Traefik
Extrae información de los archivos YAML de Traefik
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from rich.console import Console


def parse_traefik_config(config_file: Path) -> Optional[Dict[str, Any]]:
    """
    Parsea un archivo YAML de Traefik
    
    Args:
        config_file: Ruta al archivo YAML
    
    Returns:
        Dict con configuración parseada o None si hay error
    """
    if not config_file.exists():
        return None
    
    try:
        with open(config_file, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def extract_domain_from_traefik(config_data: Dict[str, Any]) -> Optional[str]:
    """
    Extrae el dominio principal de una configuración de Traefik
    
    Args:
        config_data: Configuración parseada de Traefik
    
    Returns:
        Dominio o None si no se encuentra
    """
    routers = config_data.get("http", {}).get("routers", {})
    
    for router_name, router_config in routers.items():
        rule = router_config.get("rule", "")
        if "Host(`" in rule:
            domain = rule.split("Host(`")[1].split("`)")[0]
            return domain
    
    return None


def extract_backend_from_traefik(config_data: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Extrae información del backend desde configuración de Traefik
    
    Args:
        config_data: Configuración parseada de Traefik
    
    Returns:
        Tuple (backend_type, target)
        Si es dashboard de Traefik, retorna ("TRAEFIK", "internal")
    """
    routers = config_data.get("http", {}).get("routers", {})
    services = config_data.get("http", {}).get("services", {})
    
    # Verificar si es el dashboard de Traefik (usa api@internal)
    for router_name, router_config in routers.items():
        service = router_config.get("service", "")
        # Detectar routers del dashboard de Traefik
        if service == "api@internal" or "dashboard" in router_name.lower() or "traefik" in router_name.lower():
            return "TRAEFIK", "internal"  # Servicio interno de Traefik
    
    for service_name, service_config in services.items():
        load_balancer = service_config.get("loadBalancer", {})
        servers = load_balancer.get("servers", [])
        
        if servers:
            server_url = servers[0].get("url", "")
            
            # Determinar tipo de backend
            if "apache" in service_name.lower() or "9200" in server_url:
                return "apache", server_url.replace("http://", "")
            elif "nginx" in service_name.lower() or "9100" in server_url:
                return "nginx", server_url.replace("http://", "")
            else:
                return "unknown", server_url.replace("http://", "")
    
    return None, None


def list_traefik_sites(traefik_config_dir: Path, console: Optional[Console] = None) -> List[Dict[str, Any]]:
    """
    Lista todos los sitios configurados en Traefik
    
    Args:
        traefik_config_dir: Directorio con configuraciones de Traefik
        console: Console de Rich para salida
    
    Returns:
        Lista de dicts con información de sitios
    """
    sites = []
    
    if not traefik_config_dir.exists():
        return sites
    
    # Buscar archivos YAML de Traefik
    for yaml_file in traefik_config_dir.glob("*.yml"):
        # Ignorar archivos de ejemplo y configuración base
        if yaml_file.name.startswith("01-") or yaml_file.name in ["example", "01-example-domain.yml"]:
            continue
        
        config_data = parse_traefik_config(yaml_file)
        
        if not config_data:
            continue
        
        domain = extract_domain_from_traefik(config_data)
        
        if not domain:
            continue
        
        backend_type, target = extract_backend_from_traefik(config_data)
        
        # Incluir todos los sitios, incluso el dashboard de Traefik
        sites.append({
            "domain": domain,
            "backend_type": backend_type or "N/A",
            "target": target or "N/A",
            "traefik_file": yaml_file.name,
            "traefik_path": str(yaml_file)
        })
    
    return sites
