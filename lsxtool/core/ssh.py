"""
Módulo SSH - Gestión de conexiones SSH y ejecución remota
"""

import subprocess
from typing import Optional, Dict, Tuple
from pathlib import Path
from rich.console import Console


class SSHError(Exception):
    """Excepción para errores SSH"""
    pass


def ssh_execute(
    host: str,
    user: str,
    command: str,
    password: Optional[str] = None,
    key_path: Optional[Path] = None,
    timeout: int = 30,
    console: Optional[Console] = None
) -> Tuple[bool, str, str]:
    """
    Ejecuta un comando remoto vía SSH
    
    Args:
        host: Hostname o IP del servidor
        user: Usuario SSH
        command: Comando a ejecutar
        password: Contraseña SSH (opcional, requiere sshpass)
        key_path: Ruta a clave SSH privada
        timeout: Timeout en segundos
        console: Console de Rich para salida
    
    Returns:
        Tuple (success, stdout, stderr)
    """
    ssh_cmd = ["ssh"]
    
    # Opciones SSH
    ssh_options = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes" if not password else "BatchMode=no"
    ]
    
    if key_path and key_path.exists():
        ssh_options.extend(["-i", str(key_path)])
    
    # Construir comando completo
    ssh_target = f"{user}@{host}"
    full_cmd = ssh_cmd + ssh_options + [ssh_target, command]
    
    # Si hay contraseña, usar sshpass
    if password:
        full_cmd = ["sshpass", "-p", password] + full_cmd
    
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout al ejecutar comando SSH"
    except FileNotFoundError:
        return False, "", "Comando ssh no encontrado. Instala openssh-client"
    except Exception as e:
        return False, "", f"Error SSH: {str(e)}"


def ssh_copy_file(
    host: str,
    user: str,
    local_path: Path,
    remote_path: Path,
    password: Optional[str] = None,
    key_path: Optional[Path] = None,
    console: Optional[Console] = None
) -> bool:
    """
    Copia un archivo al servidor remoto usando SCP
    
    Args:
        host: Hostname o IP del servidor
        user: Usuario SSH
        local_path: Ruta local del archivo
        remote_path: Ruta remota destino
        password: Contraseña SSH (opcional)
        key_path: Ruta a clave SSH privada
        console: Console de Rich para salida
    
    Returns:
        True si la copia fue exitosa
    """
    if not local_path.exists():
        if console:
            console.print(f"[red]✘ Archivo local no existe: {local_path}[/red]")
        return False
    
    scp_cmd = ["scp"]
    
    # Opciones SCP
    scp_options = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10"
    ]
    
    if key_path and key_path.exists():
        scp_options.extend(["-i", str(key_path)])
    
    scp_target = f"{user}@{host}:{remote_path}"
    full_cmd = scp_cmd + scp_options + [str(local_path), scp_target]
    
    # Si hay contraseña, usar sshpass
    if password:
        full_cmd = ["sshpass", "-p", password] + full_cmd
    
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False
        )
        
        if result.returncode == 0:
            if console:
                console.print(f"[green]✔ Archivo copiado: {local_path} → {user}@{host}:{remote_path}[/green]")
            return True
        else:
            if console:
                console.print(f"[red]✘ Error al copiar archivo: {result.stderr}[/red]")
            return False
    except Exception as e:
        if console:
            console.print(f"[red]✘ Error SCP: {e}[/red]")
        return False


def ssh_test_connection(
    host: str,
    user: str,
    password: Optional[str] = None,
    key_path: Optional[Path] = None,
    console: Optional[Console] = None
) -> bool:
    """
    Prueba la conexión SSH a un servidor
    
    Args:
        host: Hostname o IP del servidor
        user: Usuario SSH
        password: Contraseña SSH (opcional)
        key_path: Ruta a clave SSH privada
        console: Console de Rich para salida
    
    Returns:
        True si la conexión es exitosa
    """
    success, stdout, stderr = ssh_execute(
        host=host,
        user=user,
        command="echo 'SSH connection test'",
        password=password,
        key_path=key_path,
        timeout=10,
        console=console
    )
    
    if success:
        if console:
            console.print(f"[green]✔ Conexión SSH exitosa: {user}@{host}[/green]")
        return True
    else:
        if console:
            console.print(f"[red]✘ Error de conexión SSH: {stderr}[/red]")
        return False
