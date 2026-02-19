"""
Módulo para montajes SSHFS
Lógica de montaje y desmontaje de sistemas de archivos remotos vía SSH
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple
from rich.console import Console
from rich.panel import Panel

from .checks import check_mount_point, verify_mount_access


def create_mount_point(mount_point: Path, console: Console) -> bool:
    """
    Crea el directorio de montaje si no existe
    
    Args:
        mount_point: Ruta del punto de montaje
        console: Console de Rich para salida
    
    Returns:
        True si se creó o ya existía, False en caso de error
    """
    try:
        if mount_point.exists():
            if mount_point.is_dir():
                console.print(f"[dim]El directorio {mount_point} ya existe[/dim]")
                return True
            else:
                console.print(f"[red]✘[/red] {mount_point} existe pero no es un directorio")
                return False
        
        # Crear directorio y padres si es necesario
        mount_point.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✔[/green] Directorio creado: {mount_point}")
        return True
    except PermissionError:
        console.print(f"[red]✘[/red] Sin permisos para crear {mount_point}")
        return False
    except Exception as e:
        console.print(f"[red]✘[/red] Error al crear directorio: {e}")
        return False


def unmount_existing(mount_point: Path, console: Console) -> bool:
    """
    Desmonta un punto de montaje existente
    
    Args:
        mount_point: Ruta del punto de montaje
        console: Console de Rich para salida
    
    Returns:
        True si se desmontó correctamente o no estaba montado, False en caso de error
    """
    is_mounted, mount_info = check_mount_point(mount_point, console)
    
    if not is_mounted:
        return True
    
    console.print(f"[yellow]⚠[/yellow] Punto de montaje existente detectado")
    if mount_info:
        console.print(f"[dim]  {mount_info}[/dim]")
    
    console.print("[cyan]Desmontando punto de montaje existente...[/cyan]")
    
    try:
        # Intentar desmontar con fusermount primero (más seguro para FUSE)
        result = subprocess.run(
            ["fusermount", "-u", str(mount_point)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            console.print("[green]✔[/green] Punto de montaje desmontado correctamente")
            return True
        
        # Si fusermount falla, intentar con umount
        result = subprocess.run(
            ["umount", str(mount_point)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            console.print("[green]✔[/green] Punto de montaje desmontado correctamente")
            return True
        else:
            console.print("[red]✘[/red] Error al desmontar")
            if result.stderr:
                console.print(f"[dim]{result.stderr.strip()}[/dim]")
            return False
    except FileNotFoundError:
        console.print("[red]✘[/red] Comando de desmontaje no encontrado")
        return False
    except Exception as e:
        console.print(f"[red]✘[/red] Error al desmontar: {e}")
        return False


def mount_sshfs(
    server_ip: str,
    username: str,
    remote_path: str,
    local_path: Path,
    password: Optional[str] = None,
    console: Console = None
) -> Tuple[bool, Optional[str]]:
    """
    Monta un sistema de archivos remoto usando SSHFS
    
    Args:
        server_ip: IP o hostname del servidor remoto
        username: Usuario SSH
        remote_path: Ruta remota a montar
        local_path: Ruta local donde montar
        password: Contraseña SSH (opcional, se puede usar sshpass)
        console: Console de Rich para salida
    
    Returns:
        Tuple (success, error_message)
        - success: True si el montaje fue exitoso
        - error_message: Mensaje de error o None
    """
    if console is None:
        from rich.console import Console
        console = Console()
    
    # Construir comando sshfs
    remote_spec = f"{username}@{server_ip}:{remote_path}"
    
    # Opciones seguras de SSHFS
    # Obtener UID y GID del usuario actual
    current_uid = os.getuid()
    current_gid = os.getgid()
    
    sshfs_options = [
        "-o", "reconnect",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "default_permissions",
        "-o", f"uid={current_uid}",
        "-o", f"gid={current_gid}",
        "-o", "cache=yes",
        "-o", "cache_timeout=60",
    ]
    
    # allow_other solo si el usuario tiene permisos (requiere user_allow_other en /etc/fuse.conf)
    # Por ahora lo omitimos para evitar problemas de permisos
    
    # Construir comando completo
    cmd = ["sshfs", remote_spec, str(local_path)] + sshfs_options
    
    # Si hay contraseña, usar sshpass
    if password:
        cmd = ["sshpass", "-p", password] + cmd
    
    console.print(f"\n[cyan]Ejecutando montaje SSHFS...[/cyan]")
    console.print(f"[dim]  Remoto: {remote_spec}[/dim]")
    console.print(f"[dim]  Local:  {local_path}[/dim]")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            console.print("[green]✔[/green] Montaje SSHFS ejecutado")
            return True, None
        else:
            error_msg = result.stderr.strip() if result.stderr else "Error desconocido"
            console.print(f"[red]✘[/red] Error en montaje SSHFS")
            console.print(f"[dim]{error_msg}[/dim]")
            return False, error_msg
    except FileNotFoundError:
        error_msg = "Comando sshfs no encontrado. Verifica que esté instalado."
        console.print(f"[red]✘[/red] {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error al ejecutar sshfs: {e}"
        console.print(f"[red]✘[/red] {error_msg}")
        return False, error_msg


def mount_sshfs_interactive(console: Console) -> Tuple[bool, Optional[str]]:
    """
    Flujo interactivo completo para montar SSHFS
    
    Returns:
        Tuple (success, error_message)
    """
    from rich.prompt import Prompt
    
    console.print(Panel.fit("[bold cyan]Montaje SSHFS - Configuración[/bold cyan]", border_style="cyan"))
    
    # Paso 1/4: IP del servidor
    console.print("\n[bold]Paso 1/4:[/bold] Información del servidor remoto")
    server_ip = Prompt.ask("IP o hostname del servidor remoto")
    
    if not server_ip:
        return False, "IP del servidor es requerida"
    
    # Paso 2/4: Usuario SSH
    console.print("\n[bold]Paso 2/4:[/bold] Usuario SSH")
    username = Prompt.ask("Usuario SSH", default=os.getenv("USER", "root"))
    
    if not username:
        return False, "Usuario SSH es requerido"
    
    # Paso 3/4: Ruta remota
    console.print("\n[bold]Paso 3/4:[/bold] Ruta remota")
    remote_path = Prompt.ask("Ruta remota a montar", default="/home")
    
    if not remote_path:
        return False, "Ruta remota es requerida"
    
    # Paso 4/4: Ruta local
    console.print("\n[bold]Paso 4/4:[/bold] Punto de montaje local")
    local_path_str = Prompt.ask(
        "Ruta local donde montar",
        default=f"/mnt/sshfs/{server_ip.replace('.', '-')}"
    )
    
    if not local_path_str:
        return False, "Ruta local es requerida"
    
    local_path = Path(local_path_str)
    
    # Resumen
    console.print("\n[bold cyan]Resumen de configuración:[/bold cyan]")
    summary_table = {
        "Servidor": f"{username}@{server_ip}",
        "Ruta remota": remote_path,
        "Punto de montaje local": str(local_path)
    }
    
    for key, value in summary_table.items():
        console.print(f"  [cyan]{key}:[/cyan] {value}")
    
    from rich.prompt import Confirm
    if not Confirm.ask("\n¿Continuar con el montaje?", default=True):
        return False, "Operación cancelada por el usuario"
    
    # Verificar si ya está montado
    is_mounted, mount_info = check_mount_point(local_path, console)
    
    if is_mounted:
        console.print("\n[yellow]⚠ Punto de montaje ya está montado[/yellow]")
        if mount_info:
            console.print(f"[dim]{mount_info}[/dim]")
        
        # Verificar si responde
        if verify_mount_access(local_path, console):
            console.print("[green]✔ El montaje existente funciona correctamente[/green]")
            return True, None
        
        # Si no responde, desmontar
        console.print("[yellow]El montaje no responde, desmontando...[/yellow]")
        if not unmount_existing(local_path, console):
            return False, "No se pudo desmontar el punto de montaje existente"
    
    # Crear directorio de montaje
    if not create_mount_point(local_path, console):
        return False, "No se pudo crear el directorio de montaje"
    
    # Preguntar por contraseña (opcional, se puede usar clave SSH)
    password = None
    use_password = Confirm.ask("\n¿Usar contraseña SSH? (si no, se usará clave SSH)", default=False)
    
    if use_password:
        from getpass import getpass
        password = getpass("Contraseña SSH: ")
    
    # Ejecutar montaje
    success, error_msg = mount_sshfs(
        server_ip=server_ip,
        username=username,
        remote_path=remote_path,
        local_path=local_path,
        password=password,
        console=console
    )
    
    if not success:
        return False, error_msg
    
    # Verificar montaje post-ejecución
    console.print("\n[cyan]Verificando montaje...[/cyan]")
    
    is_mounted, mount_info = check_mount_point(local_path, console)
    
    if not is_mounted:
        return False, "El montaje no se detectó después de la ejecución"
    
    if mount_info:
        console.print(f"[green]✔ Montaje detectado:[/green]")
        console.print(f"[dim]  {mount_info}[/dim]")
    
    # Verificar acceso
    if not verify_mount_access(local_path, console):
        return False, "El punto de montaje no es accesible"
    
    console.print("\n[bold green]✅ Montaje SSHFS completado exitosamente[/bold green]")
    console.print(f"[cyan]Punto de montaje:[/cyan] {local_path}")
    
    # Registrar montaje en el sistema de gestión
    try:
        from .mount_manager import add_mount, MountInfo
        mount_info = MountInfo(
            name=f"{server_ip}-{username}",
            mount_type="sshfs",
            source=f"{username}@{server_ip}:{remote_path}",
            destination=local_path
        )
        add_mount(mount_info)
    except Exception as e:
        console.print(f"[yellow]⚠ No se pudo registrar el montaje: {e}[/yellow]")
    
    return True, None
