#!/usr/bin/env python3
"""
Módulo CLI para montajes - LSX Tool
Gestión de montajes de sistemas de archivos (SSHFS, NFS, CIFS, etc.)
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional

from .checks import check_wsl, verify_dependencies_with_install, check_mount_point, verify_mount_access
from .sshfs import mount_sshfs_interactive
from .mount_manager import (
    list_mounts,
    get_mount,
    remove_mount,
    add_mount,
    update_mount_check,
    MountInfo
)

app = typer.Typer(
    name="mount",
    help=(
        "Gestión de montajes de sistemas de archivos\n\n"
        "Este módulo permite gestionar montajes de sistemas de archivos remotos\n"
        "y locales, incluyendo SSHFS, bind mounts y otros tipos de volúmenes.\n\n"
        "Los montajes gestionados por lsxtool se registran y pueden ser listados,\n"
        "verificados y removidos de forma centralizada.\n\n"
        "⚠️  Algunas operaciones requieren permisos de root."
    ),
    add_completion=False,
    no_args_is_help=True
)
console = Console()


@app.command()
def list():
    """
    Lista todos los montajes gestionados por lsxtool
    
    Muestra tipo, origen, destino y estado de cada montaje.
    """
    console.print(Panel.fit("[bold cyan]Montajes Gestionados[/bold cyan]", border_style="cyan"))
    
    mounts = list_mounts()
    
    if not mounts:
        console.print("[yellow]⚠️ No hay montajes registrados[/yellow]")
        console.print("[dim]Usa 'lsxtool servers mount add' para crear un montaje[/dim]")
        return
    
    table = Table(title="Montajes Registrados", show_header=True, header_style="bold cyan")
    table.add_column("Nombre", style="cyan", width=20)
    table.add_column("Tipo", style="yellow")
    table.add_column("Origen", style="green")
    table.add_column("Destino", style="blue")
    table.add_column("Estado", style="green")
    
    for mount in mounts:
        # Verificar estado del montaje
        is_mounted, _ = check_mount_point(mount.destination, console)
        status = "[green]✅ Montado[/green]" if is_mounted else "[red]❌ No montado[/red]"
        
        table.add_row(
            mount.name,
            mount.mount_type.upper(),
            mount.source[:40] + "..." if len(mount.source) > 40 else mount.source,
            str(mount.destination),
            status
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(mounts)} montaje(s)[/dim]")


@app.command()
def add(
    mount_type: str = typer.Argument(..., help="Tipo de montaje (sshfs, bind, nfs, etc.)")
):
    """
    Crea y configura un nuevo montaje
    
    Soporta SSHFS, bind mounts y otros tipos de filesystem.
    
    Ejemplo: lsxtool servers mount add sshfs
    """
    mount_type_lower = mount_type.lower()
    
    if mount_type_lower == "sshfs":
        console.print(Panel.fit("[bold cyan]Crear Montaje SSHFS[/bold cyan]", border_style="cyan"))
        
        # Verificación de entorno
        console.print("\n[bold]Verificación de entorno[/bold]")
        check_wsl(console)
        
        # Verificación de dependencias
        if not verify_dependencies_with_install(console):
            console.print("\n[red]❌ No se pueden continuar sin las dependencias necesarias[/red]")
            console.print("[yellow]Instala manualmente: sudo apt-get install sshfs fuse sshpass[/yellow]")
            raise typer.Exit(code=1)
        
        # Ejecutar flujo interactivo
        success, error_msg = mount_sshfs_interactive(console)
        
        if not success:
            console.print(f"\n[bold red]❌ Error en montaje SSHFS[/bold red]")
            if error_msg:
                console.print(f"[red]{error_msg}[/red]")
            raise typer.Exit(code=1)
    else:
        console.print(f"[red]❌ Tipo de montaje '{mount_type}' no soportado aún[/red]")
        console.print("[yellow]Tipos disponibles: sshfs[/yellow]")
        raise typer.Exit(code=1)
    
    console.print()


@app.command()
def remove(
    destination: str = typer.Argument(..., help="Ruta del punto de montaje a eliminar")
):
    """
    Desmonta y elimina un montaje gestionado
    
    Desmonta el filesystem y remueve la configuración.
    Requiere confirmación antes de eliminar.
    """
    import os
    import subprocess
    from rich.prompt import Confirm
    
    console.print(Panel.fit(f"[bold cyan]Eliminar Montaje[/bold cyan]", border_style="cyan"))
    
    dest_path = Path(destination)
    
    mount_info = get_mount(dest_path)
    
    if not mount_info:
        console.print(f"[red]❌ Montaje en '{destination}' no encontrado en el registro[/red]")
        console.print("[yellow]Usa 'lsxtool servers mount list' para ver montajes registrados[/yellow]")
        raise typer.Exit(code=1)
    
    console.print(f"[cyan]Montaje encontrado:[/cyan]")
    console.print(f"  Tipo: {mount_info.mount_type}")
    console.print(f"  Origen: {mount_info.source}")
    console.print(f"  Destino: {mount_info.destination}")
    
    # Verificar si está montado
    is_mounted, _ = check_mount_point(dest_path, console)
    
    if is_mounted:
        if not Confirm.ask("\n¿Desmontar antes de eliminar?", default=True):
            console.print("[yellow]Operación cancelada[/yellow]")
            return
        
        console.print("[cyan]Desmontando...[/cyan]")
        try:
            # Intentar fusermount primero
            result = subprocess.run(
                ["fusermount", "-u", str(dest_path)],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                # Intentar umount
                result = subprocess.run(
                    ["umount", str(dest_path)],
                    capture_output=True,
                    text=True,
                    check=False
                )
            
            if result.returncode == 0:
                console.print("[green]✔ Montaje desmontado[/green]")
            else:
                console.print("[yellow]⚠ No se pudo desmontar automáticamente[/yellow]")
                if not Confirm.ask("¿Continuar eliminando del registro?", default=False):
                    return
        except Exception as e:
            console.print(f"[yellow]⚠ Error al desmontar: {e}[/yellow]")
            if not Confirm.ask("¿Continuar eliminando del registro?", default=False):
                return
    
    if not Confirm.ask(f"\n¿Eliminar montaje '{mount_info.name}' del registro?", default=False):
        console.print("[yellow]Operación cancelada[/yellow]")
        return
    
    if remove_mount(dest_path):
        console.print(f"\n[green]✅ Montaje eliminado del registro[/green]")
    else:
        console.print(f"\n[red]❌ Error al eliminar montaje[/red]")
        raise typer.Exit(code=1)


@app.command()
def status(
    destination: Optional[str] = typer.Argument(None, help="Ruta del punto de montaje (opcional, muestra todos si no se especifica)")
):
    """
    Valida el estado de un montaje específico
    
    Verifica si está montado, accesible y funcionando correctamente.
    """
    console.print(Panel.fit("[bold cyan]Estado de Montajes[/bold cyan]", border_style="cyan"))
    
    if destination:
        dest_path = Path(destination)
        mount_info = get_mount(dest_path)
        
        if not mount_info:
            console.print(f"[red]❌ Montaje en '{destination}' no encontrado[/red]")
            raise typer.Exit(code=1)
        
        mounts_to_check = [mount_info]
    else:
        mounts_to_check = list_mounts()
        
        if not mounts_to_check:
            console.print("[yellow]⚠️ No hay montajes registrados[/yellow]")
            return
    
    for mount_info in mounts_to_check:
        console.print(f"\n[bold]{mount_info.name}[/bold]")
        console.print(f"  Tipo: {mount_info.mount_type}")
        console.print(f"  Origen: {mount_info.source}")
        console.print(f"  Destino: {mount_info.destination}")
        
        # Verificar montaje
        is_mounted, mount_info_str = check_mount_point(mount_info.destination, console)
        
        if is_mounted:
            console.print(f"  Estado: [green]✅ Montado[/green]")
            if mount_info_str:
                console.print(f"  [dim]{mount_info_str}[/dim]")
            
            # Verificar acceso
            if verify_mount_access(mount_info.destination, console):
                update_mount_check(mount_info.destination)
        else:
            console.print(f"  Estado: [red]❌ No montado[/red]")


@app.command()
def check():
    """
    Verifica dependencias y requisitos del sistema
    
    Comprueba herramientas necesarias (sshfs, fusermount, permisos).
    Ofrece instalación automática si faltan dependencias.
    """
    console.print(Panel.fit("[bold cyan]Verificación de Dependencias[/bold cyan]", border_style="cyan"))
    
    # Verificación de entorno
    console.print("\n[bold]Entorno[/bold]")
    check_wsl(console)
    
    # Verificación de dependencias
    console.print("\n[bold]Dependencias[/bold]")
    if verify_dependencies_with_install(console):
        console.print("\n[bold green]✅ Todas las dependencias están disponibles[/bold green]")
    else:
        console.print("\n[yellow]⚠️ Algunas dependencias faltan[/yellow]")
        console.print("[dim]Ejecuta con sudo para instalar automáticamente[/dim]")


@app.command()
def sshfs():
    """
    Monta un sistema de archivos remoto usando SSHFS
    
    Flujo interactivo guiado para configuración de montaje SSHFS.
    """
    console.print(Panel.fit("[bold cyan]Montaje SSHFS[/bold cyan]", border_style="cyan"))
    
    # Verificación de entorno
    console.print("\n[bold]Verificación de entorno[/bold]")
    check_wsl(console)
    
    # Verificación de dependencias
    if not verify_dependencies_with_install(console):
        console.print("\n[red]❌ No se pueden continuar sin las dependencias necesarias[/red]")
        console.print("[yellow]Instala manualmente: sudo apt-get install sshfs fuse sshpass[/yellow]")
        raise typer.Exit(code=1)
    
    # Ejecutar flujo interactivo
    success, error_msg = mount_sshfs_interactive(console)
    
    if not success:
        console.print(f"\n[bold red]❌ Error en montaje SSHFS[/bold red]")
        if error_msg:
            console.print(f"[red]{error_msg}[/red]")
        raise typer.Exit(code=1)
    
    console.print()


if __name__ == "__main__":
    app()
