"""
Parser de archivos de configuración Nginx
Extrae información estructurada de archivos .conf
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Importar meta_parser usando import relativo
from ..sites.meta_parser import parse_meta_from_conf

from .rules.base import NginxConfig


def parse_nginx_config(config_file: Path) -> Optional[NginxConfig]:
    """
    Parsea un archivo de configuración Nginx
    
    Args:
        config_file: Ruta al archivo .conf
    
    Returns:
        NginxConfig parseado o None si hay error
    """
    if not config_file.exists():
        return None
    
    try:
        content = config_file.read_text()
        
        # Parsear META
        meta = parse_meta_from_conf(config_file) or {}
        
        # Parsear server_name
        server_name = _extract_server_name(content)
        
        # Parsear upstreams
        upstreams = _extract_upstreams(content)
        
        # Parsear proxy_pass
        proxy_pass = _extract_proxy_pass(content)
        
        # Parsear logs
        access_log = _extract_access_log(content)
        error_log = _extract_error_log(content)
        
        return NginxConfig(
            file_path=config_file,
            content=content,
            meta=meta,
            server_name=server_name,
            upstreams=upstreams,
            proxy_pass=proxy_pass,
            access_log=access_log,
            error_log=error_log
        )
    except Exception:
        return None


def _extract_server_name(content: str) -> Optional[str]:
    """Extrae server_name del contenido"""
    # Buscar: server_name dominio.com;
    pattern = r'server_name\s+([^;]+);'
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        # Limpiar espacios y tomar el primer dominio
        server_name = match.group(1).strip().split()[0]
        return server_name
    return None


def _extract_upstreams(content: str) -> Dict[str, Dict]:
    """Extrae todos los upstreams del contenido"""
    upstreams = {}
    
    # Buscar bloques upstream
    pattern = r'upstream\s+(\w+)\s*\{([^}]+)\}'
    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
    
    for match in matches:
        name = match.group(1)
        block_content = match.group(2)
        
        # Extraer servidores
        servers = []
        server_pattern = r'server\s+([^;]+);'
        server_matches = re.finditer(server_pattern, block_content)
        for server_match in server_matches:
            server_line = server_match.group(1).strip()
            servers.append(server_line)
        
        upstreams[name] = {
            "servers": servers,
            "content": block_content
        }
    
    return upstreams


def _extract_proxy_pass(content: str) -> Optional[str]:
    """Extrae proxy_pass del contenido"""
    # Buscar: proxy_pass http://...; o proxy_pass upstream_name;
    pattern = r'proxy_pass\s+([^;]+);'
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        proxy_pass = match.group(1).strip()
        # Si no tiene http://, asumir que es un upstream
        if not proxy_pass.startswith("http://") and not proxy_pass.startswith("https://"):
            # Es un upstream, agregar http:// para consistencia
            proxy_pass = f"http://{proxy_pass}"
        return proxy_pass
    return None


def _extract_access_log(content: str) -> Optional[str]:
    """Extrae access_log del contenido"""
    # Buscar: access_log /path/to/log;
    pattern = r'access_log\s+([^;]+);'
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        log_path = match.group(1).strip()
        # Remover parámetros adicionales (ej: combined)
        log_path = log_path.split()[0]
        return log_path
    return None


def _extract_error_log(content: str) -> Optional[str]:
    """Extrae error_log del contenido"""
    # Buscar: error_log /path/to/log;
    pattern = r'error_log\s+([^;]+);'
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        log_path = match.group(1).strip()
        # Remover nivel de log (ej: warn)
        log_path = log_path.split()[0]
        return log_path
    return None


def extract_location_routes(content: str) -> Dict[str, str]:
    """
    Extrae location path → upstream name desde bloques location { ... proxy_pass http://upstream; }.
    Retorna dict path -> upstream (ej: '/' -> 'api__identity', '/api/identity/' -> 'api__identity').
    """
    out = {}
    # Buscar location PATH { ... } (soporta anidado mínimo: solo primer nivel)
    pattern = r'location\s+([^\s{]+)\s*\{'
    for m in re.finditer(pattern, content):
        path = m.group(1).strip()
        start = m.end()
        depth = 1
        i = start
        while i < len(content) and depth > 0:
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    block = content[start:i]
                    pp = re.search(r'proxy_pass\s+(?:https?://)?([^\s;]+)', block)
                    if pp:
                        upstream = pp.group(1).rstrip('/;').strip()
                        out[path] = upstream
                    break
            i += 1
    return out


def find_nginx_configs(base_dir: Path) -> List[Path]:
    """
    Encuentra todos los archivos .conf de Nginx gestionados por LSX
    
    Args:
        base_dir: Directorio base del proyecto
    
    Returns:
        Lista de rutas a archivos .conf
    """
    configs = []
    
    # Buscar en la estructura estándar de LSX
    nginx_config_dir = base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d"
    
    if nginx_config_dir.exists():
        # Buscar recursivamente archivos .conf
        for conf_file in nginx_config_dir.rglob("*.conf"):
            # Ignorar archivos de snippets y templates
            if "snippets" not in str(conf_file) and "templates" not in str(conf_file):
                configs.append(conf_file)
    
    return sorted(configs)
