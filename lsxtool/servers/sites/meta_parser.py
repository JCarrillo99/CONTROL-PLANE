"""
Parser de metadatos desde comentarios estructurados en archivos .conf
Formato: LSX META block en comentarios
"""

import re
from pathlib import Path
from typing import Dict, Optional, List
from rich.console import Console


META_START = "# --- LSX META ---"
META_END = "# --- END META ---"


def parse_meta_from_conf(config_file: Path) -> Optional[Dict[str, str]]:
    """
    Parsea metadatos desde un archivo de configuración
    
    Args:
        config_file: Ruta al archivo .conf
    
    Returns:
        Dict con metadatos parseados o None si no existe bloque META
    """
    if not config_file.exists():
        return None
    
    try:
        content = config_file.read_text()
        
        # Buscar bloque META
        start_idx = content.find(META_START)
        end_idx = content.find(META_END)
        
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            return None
        
        # Extraer bloque META
        meta_block = content[start_idx:end_idx + len(META_END)]
        
        # Parsear líneas de metadatos
        meta = {}
        for line in meta_block.split("\n"):
            line = line.strip()
            # Buscar líneas con formato: # key: value
            if line.startswith("#") and ":" in line:
                # Remover # y espacios
                line = line[1:].strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        meta[key] = value
        
        return meta if meta else None
        
    except Exception:
        return None


def write_meta_to_conf(config_file: Path, meta: Dict[str, str], console: Optional[Console] = None) -> bool:
    """
    Escribe metadatos a un archivo de configuración
    
    Args:
        config_file: Ruta al archivo .conf
        meta: Dict con metadatos a escribir
        console: Console de Rich para salida
    
    Returns:
        True si se escribió correctamente
    """
    if not config_file.exists():
        if console:
            console.print(f"[yellow]⚠️ Archivo no existe: {config_file}[/yellow]")
        return False
    
    try:
        content = config_file.read_text()
        
        # Buscar si ya existe bloque META
        start_idx = content.find(META_START)
        end_idx = content.find(META_END)
        
        # Construir bloque META
        meta_lines = [META_START]
        for key, value in sorted(meta.items()):
            meta_lines.append(f"# {key}: {value}")
        meta_lines.append(META_END)
        meta_block = "\n".join(meta_lines) + "\n"
        
        if start_idx != -1 and end_idx != -1:
            # Reemplazar bloque existente
            content = content[:start_idx] + meta_block + content[end_idx + len(META_END):].lstrip()
        else:
            # Agregar al inicio del archivo
            content = meta_block + content

        # Sincronizar puerto en bloques upstream (tech_port, node_port, php_port, etc.)
        content = _apply_upstream_port_sync(content, meta)

        # Escribir archivo
        config_file.write_text(content)

        if console:
            console.print(f"[green]✅ Metadatos escritos en {config_file.name}[/green]")

        return True

    except Exception as e:
        if console:
            console.print(f"[red]❌ Error al escribir metadatos: {e}[/red]")
        return False


def _apply_upstream_port_sync(content: str, meta: Dict[str, str]) -> str:
    """
    En el contenido del .conf, actualiza los puertos en bloques upstream para que
    coincidan con META (tech_port, node_port, php_port, python_port, etc.).
    Todas las líneas 'server IP:PUERTO' del bloque (principal, backup, balanceador)
    se actualizan al mismo puerto; se asume que es la misma aplicación.
    """
    port_key = None
    for key in ["tech_port", "node_port", "php_port", "python_port"]:
        if key in meta and meta[key]:
            port_key = key
            break
    if not port_key:
        return content

    new_port = meta[port_key].strip()
    if not new_port.isdigit():
        return content

    def replace_ports_in_upstream(match: re.Match) -> str:
        block = match.group(0)
        # Reemplazar todo server IP:PUERTO (incl. backup, weight=..., etc.) por el puerto de META
        return re.sub(r"(\bserver\s+[^\s:]+:)\d+", rf"\g<1>{new_port}", block)

    pattern = re.compile(r"upstream\s+\w+\s*\{[^}]*\}", re.MULTILINE | re.DOTALL)
    return pattern.sub(replace_ports_in_upstream, content)


def validate_meta(meta: Dict[str, str], console: Optional[Console] = None) -> tuple[bool, List[str]]:
    """
    Valida metadatos
    
    Args:
        meta: Dict con metadatos a validar
        console: Console de Rich para salida
    
    Returns:
        Tuple (es_válido, lista_de_advertencias)
    """
    warnings = []
    required_fields = ["owner", "provider"]
    recommended_fields = ["service_type", "environment", "server_web", "server_web_version"]
    
    # Validar campos requeridos
    missing_required = [field for field in required_fields if field not in meta or not meta[field]]
    if missing_required:
        warnings.append(f"Campos requeridos faltantes: {', '.join(missing_required)}")
    
    # Campos recomendados: aceptar server_web o backend (compat)
    meta_has_sw = meta.get("server_web") or meta.get("backend")
    missing_recommended = [f for f in recommended_fields if f not in meta or not meta[f]]
    if not meta_has_sw:
        missing_recommended.append("server_web")
    if missing_recommended:
        warnings.append(f"Campos recomendados faltantes: {', '.join(missing_recommended)}")
    
    # Validar valores específicos
    if "environment" in meta:
        valid_envs = ["dev", "qa", "prod"]
        if meta["environment"] not in valid_envs:
            warnings.append(f"Ambiente inválido: {meta['environment']}. Debe ser uno de: {', '.join(valid_envs)}")
    
    sw = meta.get("server_web") or meta.get("backend")
    if sw:
        valid_servers = ["apache", "nginx", "caddy", "traefik"]
        if sw.lower() not in valid_servers:
            warnings.append(f"Server web inválido: {sw}. Debe ser uno de: {', '.join(valid_servers)}")
    
    is_valid = len(missing_required) == 0
    
    if console and warnings:
        for warning in warnings:
            console.print(f"[yellow]⚠️ {warning}[/yellow]")
    
    return is_valid, warnings


def meta_to_manifest_dict(meta: Dict[str, str], domain: str) -> Dict:
    """
    Convierte metadatos parseados a formato de ServiceManifest
    
    Args:
        meta: Dict con metadatos parseados
        domain: Dominio del sitio
    
    Returns:
        Dict con campos para ServiceManifest
    """
    sw = (meta.get("server_web") or meta.get("backend") or "unknown").lower()
    sw_version = meta.get("server_web_version") or meta.get("backend_version")
    return {
        "domain": domain,
        "owner": meta.get("owner"),
        "provider": meta.get("provider", "EXTERNAL"),
        "service_type": meta.get("service_type", "web"),
        "server_web": sw,
        "server_web_version": sw_version,
        "backend_type": sw,  # compat
        "backend_version": sw_version,  # compat
        "tech": meta.get("tech"),
        "tech_version": meta.get("tech_version"),
        "environment": meta.get("environment", "dev"),
        "description": meta.get("description", f"Sitio {domain}"),
    }
