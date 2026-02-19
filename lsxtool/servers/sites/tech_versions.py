"""
Módulo para detectar versiones de tecnologías disponibles en el sistema
"""

import subprocess
from pathlib import Path
from typing import List, Optional


def get_php_versions() -> List[str]:
    """
    Detecta versiones de PHP-FPM disponibles en el sistema
    Busca sockets en /var/run/php/
    
    Returns:
        Lista de versiones de PHP disponibles (ej: ['7.4', '8.2', '8.3'])
    """
    php_socket_dir = Path("/var/run/php")
    versions = []
    
    if php_socket_dir.exists():
        # Buscar sockets de PHP-FPM
        for socket_file in php_socket_dir.glob("php*-fpm.sock"):
            # Extraer versión del nombre del archivo
            # Ejemplo: php8.2-fpm.sock -> 8.2
            name = socket_file.stem  # php8.2-fpm
            if "php" in name and "fpm" in name:
                # Extraer número de versión
                parts = name.replace("php", "").replace("-fpm", "").split(".")
                if len(parts) >= 2:
                    version = f"{parts[0]}.{parts[1]}"
                    if version not in versions:
                        versions.append(version)
    
    # También intentar detectar desde php-fpm instalado
    try:
        result = subprocess.run(
            ["php-fpm", "-v"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Buscar versión en la salida
            output = result.stdout
            if "PHP" in output:
                # Extraer versión (ej: PHP 8.2.0)
                import re
                match = re.search(r'PHP (\d+\.\d+)', output)
                if match:
                    version = match.group(1)
                    if version not in versions:
                        versions.insert(0, version)  # Priorizar la versión activa
    except:
        pass
    
    # Ordenar versiones (más recientes primero)
    def version_key(v):
        parts = v.split('.')
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    
    versions.sort(key=version_key, reverse=True)
    
    return versions


def get_node_versions() -> List[str]:
    """
    Detecta versiones de Node.js disponibles en el sistema
    
    Returns:
        Lista de versiones de Node.js disponibles
    """
    versions = []
    
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip().replace("v", "")
            versions.append(version)
    except:
        pass
    
    # También buscar en /usr/bin/node*
    node_bin_dir = Path("/usr/bin")
    if node_bin_dir.exists():
        for node_bin in node_bin_dir.glob("node*"):
            if node_bin.is_file() and node_bin.name.startswith("node"):
                try:
                    result = subprocess.run(
                        [str(node_bin), "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip().replace("v", "")
                        if version not in versions:
                            versions.append(version)
                except:
                    pass
    
    return versions


def get_python_versions() -> List[str]:
    """
    Detecta versiones de Python disponibles en el sistema
    
    Returns:
        Lista de versiones de Python disponibles
    """
    versions = []
    
    # Buscar python3.x en /usr/bin
    python_bin_dir = Path("/usr/bin")
    if python_bin_dir.exists():
        for python_bin in python_bin_dir.glob("python3.*"):
            if python_bin.is_file():
                version = python_bin.name.replace("python", "")
                if version not in versions:
                    versions.append(version)
        
        # También verificar python3
        python3 = python_bin_dir / "python3"
        if python3.exists():
            try:
                result = subprocess.run(
                    [str(python3), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split()[1]
                    if version not in versions:
                        versions.insert(0, version)
            except:
                pass
    
    return versions
