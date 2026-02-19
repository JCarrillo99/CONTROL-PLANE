"""
Módulo para actualizar configuraciones automáticamente basado en metadatos
Permite actualizar sockets de PHP-FPM cuando cambia tech_version
"""

import re
from pathlib import Path
from typing import Optional
from rich.console import Console

from .meta_parser import parse_meta_from_conf, write_meta_to_conf


def update_php_socket_from_meta(config_file: Path, console: Optional[Console] = None) -> bool:
    """
    Actualiza el socket de PHP-FPM en un archivo de configuración basándose en tech_version de los metadatos
    
    Args:
        config_file: Ruta al archivo .conf (Apache o Nginx)
        console: Console de Rich para salida
    
    Returns:
        True si se actualizó correctamente, False si no se pudo actualizar
    """
    if not config_file.exists():
        if console:
            console.print(f"[yellow]⚠️ Archivo no existe: {config_file}[/yellow]")
        return False
    
    # Leer metadatos
    meta = parse_meta_from_conf(config_file)
    if not meta:
        if console:
            console.print(f"[yellow]⚠️ No se encontraron metadatos en {config_file.name}[/yellow]")
        return False
    
    # Verificar que tiene tech y tech_version
    tech = meta.get("tech", "").lower()
    tech_version = meta.get("tech_version")
    
    if tech != "php" or not tech_version:
        if console:
            console.print(f"[dim]No es necesario actualizar (tech={tech}, tech_version={tech_version})[/dim]")
        return False
    
    # Extraer versión numérica (ej: "7.4" de "PHP 7.4" o "7.4")
    version_match = re.search(r'(\d+\.\d+)', str(tech_version))
    if not version_match:
        if console:
            console.print(f"[yellow]⚠️ No se pudo extraer versión numérica de: {tech_version}[/yellow]")
        return False
    
    php_version = version_match.group(1)
    
    try:
        content = config_file.read_text()
        original_content = content
        
        # Detectar tipo de configuración (Apache o Nginx)
        is_apache = "VirtualHost" in content or "SetHandler" in content
        is_nginx = "server {" in content or "fastcgi_pass" in content
        
        updated = False
        
        if is_apache:
            # Actualizar socket de Apache: SetHandler "proxy:unix:/var/run/php/phpX.X-fpm.sock|fcgi://localhost/"
            pattern = r'(SetHandler\s+"proxy:unix:/var/run/php/)php\d+\.\d+(-fpm\.sock\|fcgi://localhost/")'
            replacement = rf'\1php{php_version}\2'
            
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                updated = True
                if console:
                    console.print(f"[green]✅ Socket PHP actualizado a {php_version} en Apache[/green]")
        
        elif is_nginx:
            # Actualizar socket de Nginx: fastcgi_pass unix:/var/run/php/phpX.X-fpm.sock;
            pattern = r'(fastcgi_pass\s+unix:/var/run/php/)php\d+\.\d+(-fpm\.sock;)'
            replacement = rf'\1php{php_version}\2'
            
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                updated = True
                if console:
                    console.print(f"[green]✅ Socket PHP actualizado a {php_version} en Nginx[/green]")
        
        if updated and content != original_content:
            config_file.write_text(content)
            return True
        
        return False
        
    except Exception as e:
        if console:
            console.print(f"[red]❌ Error al actualizar socket: {e}[/red]")
        return False


def update_config_from_meta(config_file: Path, console: Optional[Console] = None) -> bool:
    """
    Actualiza configuración completa basándose en metadatos
    Por ahora solo actualiza sockets PHP, pero puede extenderse para otros casos
    
    Args:
        config_file: Ruta al archivo .conf
        console: Console de Rich para salida
    
    Returns:
        True si se actualizó algo
    """
    updated = False
    
    # Actualizar socket PHP si aplica
    if update_php_socket_from_meta(config_file, console):
        updated = True
    
    return updated
