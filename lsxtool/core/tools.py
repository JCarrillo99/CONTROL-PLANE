"""
Módulo Tools - Utilidades y helpers compartidos
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console


def ensure_directory(path: Path, console: Optional[Console] = None) -> bool:
    """
    Asegura que un directorio existe, creándolo si es necesario
    
    Args:
        path: Ruta del directorio
        console: Console de Rich para salida
    
    Returns:
        True si el directorio existe o se creó
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except PermissionError:
        if console:
            console.print(f"[red]✘ Sin permisos para crear: {path}[/red]")
        return False
    except Exception as e:
        if console:
            console.print(f"[red]✘ Error al crear directorio: {e}[/red]")
        return False


def read_file_safe(path: Path, console: Optional[Console] = None) -> Optional[str]:
    """
    Lee un archivo de forma segura
    
    Args:
        path: Ruta del archivo
        console: Console de Rich para salida
    
    Returns:
        Contenido del archivo o None si hay error
    """
    try:
        return path.read_text()
    except FileNotFoundError:
        if console:
            console.print(f"[red]✘ Archivo no encontrado: {path}[/red]")
        return None
    except Exception as e:
        if console:
            console.print(f"[red]✘ Error al leer archivo: {e}[/red]")
        return None


def write_file_safe(path: Path, content: str, console: Optional[Console] = None) -> bool:
    """
    Escribe un archivo de forma segura
    
    Args:
        path: Ruta del archivo
        content: Contenido a escribir
        console: Console de Rich para salida
    
    Returns:
        True si se escribió correctamente
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return True
    except PermissionError:
        if console:
            console.print(f"[red]✘ Sin permisos para escribir: {path}[/red]")
        return False
    except Exception as e:
        if console:
            console.print(f"[red]✘ Error al escribir archivo: {e}[/red]")
        return False


def mask_sensitive_data(text: str, mask_char: str = "*") -> str:
    """
    Enmascara datos sensibles en texto (tokens, contraseñas, etc.)
    
    Args:
        text: Texto a enmascarar
        mask_char: Carácter para enmascarar
    
    Returns:
        Texto con datos sensibles enmascarados
    """
    # Patrones comunes de tokens/contraseñas
    import re
    
    # Tokens GitLab (glpat-...)
    text = re.sub(r'glpat-[a-zA-Z0-9]{20,}', f'glpat-{mask_char * 20}', text)
    
    # Tokens genéricos (más de 20 caracteres alfanuméricos)
    text = re.sub(r'[a-zA-Z0-9]{20,}', mask_char * 20, text)
    
    # Contraseñas en variables de entorno comunes
    password_patterns = [
        r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
        r'passwd["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
        r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
    ]
    
    for pattern in password_patterns:
        text = re.sub(pattern, lambda m: m.group(0).replace(m.group(1), mask_char * len(m.group(1))), text)
    
    return text


def run_command(
    command: list,
    cwd: Optional[Path] = None,
    timeout: int = 30,
    capture_output: bool = True,
    console: Optional[Console] = None
) -> tuple[bool, str, str]:
    """
    Ejecuta un comando del sistema de forma segura
    
    Args:
        command: Lista con comando y argumentos
        cwd: Directorio de trabajo
        timeout: Timeout en segundos
        capture_output: Si capturar stdout/stderr
        console: Console de Rich para salida
    
    Returns:
        Tuple (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            check=False
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        if console:
            console.print(f"[red]✘ Timeout ejecutando: {' '.join(command)}[/red]")
        return False, "", "Timeout"
    except FileNotFoundError:
        if console:
            console.print(f"[red]✘ Comando no encontrado: {command[0]}[/red]")
        return False, "", f"Comando no encontrado: {command[0]}"
    except Exception as e:
        if console:
            console.print(f"[red]✘ Error ejecutando comando: {e}[/red]")
        return False, "", str(e)
