#!/usr/bin/env python3
"""
Módulo de Redes - LSX Tool
Gestión de DNS y configuración de red
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Optional
import sys
import os
from pathlib import Path

from .dns_manager import (
    set_dns_normal,
    set_dns_corporativo,
    get_current_dns,
    test_dns,
    DNSConfig,
    DNS_NORMAL,
    DNS_CORPORATIVO
)
from .dns_profiles import (
    load_profiles,
    add_profile,
    remove_profile,
    list_profiles,
    get_profile,
    profile_to_dns_config,
    DNSProfile
)

app = typer.Typer(
    name="networks",
    help="Gestión de Redes y DNS",
    add_completion=False
)
console = Console()

# Crear subcomando DNS con ayuda detallada
dns_app = typer.Typer(
    name="dns",
    help=(
        "Gestión de configuración DNS en WSL/Linux\n\n"
        "Este módulo permite gestionar perfiles de configuración DNS, alternando\n"
        "entre diferentes resoluciones según el contexto (corporativo, público,\n"
        "personalizado).\n\n"
        "En WSL, la configuración DNS se gestiona mediante /etc/resolv.conf y\n"
        "wsl.conf. Este módulo facilita el cambio entre perfiles predefinidos\n"
        "sin editar archivos manualmente.\n\n"
        "⚠️  Requiere permisos de root para modificar configuración del sistema."
    ),
    add_completion=False,
    no_args_is_help=True
)
app.add_typer(dns_app)


@dns_app.command()
def list():
    """
    Lista todos los perfiles DNS configurados
    
    Muestra perfiles disponibles con sus servidores DNS asociados.
    """
    console.print(Panel.fit("[bold cyan]Perfiles DNS Configurados[/bold cyan]", border_style="cyan"))
    
    profiles = list_profiles()
    
    if not profiles:
        console.print("[yellow]⚠️ No hay perfiles DNS configurados[/yellow]")
        return
    
    table = Table(title="Perfiles DNS Disponibles", show_header=True, header_style="bold cyan")
    table.add_column("Nombre", style="cyan", width=20)
    table.add_column("Descripción", style="green")
    table.add_column("Servidores DNS", style="yellow")
    
    for profile in profiles:
        servers_text = ", ".join(profile.servers[:2])
        if len(profile.servers) > 2:
            servers_text += f" (+{len(profile.servers) - 2} más)"
        
        table.add_row(
            profile.name,
            profile.description,
            servers_text
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(profiles)} perfil(es)[/dim]")


@dns_app.command()
def add():
    """
    Crea un nuevo perfil DNS personalizado
    
    Permite definir nombre, servidores DNS y dominios de búsqueda.
    """
    from rich.prompt import Prompt
    
    console.print(Panel.fit("[bold cyan]Crear Perfil DNS[/bold cyan]", border_style="cyan"))
    
    name = Prompt.ask("Nombre del perfil")
    if not name:
        console.print("[red]❌ El nombre es requerido[/red]")
        sys.exit(1)
    
    description = Prompt.ask("Descripción", default="")
    
    console.print("\n[bold]Servidores DNS (ingresa uno por línea, línea vacía para terminar):[/bold]")
    servers = []
    while True:
        server = Prompt.ask(f"  Servidor DNS {len(servers) + 1}", default="")
        if not server:
            break
        servers.append(server)
    
    if not servers:
        console.print("[red]❌ Se requiere al menos un servidor DNS[/red]")
        sys.exit(1)
    
    search_domains_input = Prompt.ask(
        "\nDominios de búsqueda (separados por espacios, opcional)",
        default=""
    )
    search_domains = [d.strip() for d in search_domains_input.split()] if search_domains_input else None
    
    profile = DNSProfile(
        name=name,
        description=description or name,
        servers=servers,
        search_domains=search_domains if search_domains else None
    )
    
    if add_profile(profile):
        console.print(f"\n[green]✅ Perfil '{name}' creado exitosamente[/green]")
    else:
        console.print(f"\n[red]❌ El perfil '{name}' ya existe[/red]")
        sys.exit(1)


@dns_app.command()
def enable(
    profile_name: str = typer.Argument(..., help="Nombre del perfil DNS a activar")
):
    """
    Activa un perfil DNS existente
    
    Aplica la configuración del perfil seleccionado al sistema.
    
    Ejemplo: lsxtool network dns enable corp
    """
    console.print(Panel.fit(f"[bold cyan]Activar Perfil DNS: {profile_name}[/bold cyan]", border_style="cyan"))
    
    profile = get_profile(profile_name)
    
    if not profile:
        console.print(f"[red]❌ Perfil '{profile_name}' no encontrado[/red]")
        console.print("[yellow]Usa 'lsxtool network dns list' para ver perfiles disponibles[/yellow]")
        sys.exit(1)
    
    try:
        dns_config = profile_to_dns_config(profile)
        
        # Usar función apropiada según el perfil
        if profile_name.lower() in ["normal", "normal/público"]:
            set_dns_normal(dns_config, console)
        elif profile_name.lower() in ["corp", "corporativo"]:
            set_dns_corporativo(dns_config, console)
        else:
            # Perfil personalizado
            from .dns_manager import write_resolv_conf
            write_resolv_conf(dns_config)
            console.print("[green]✓ Configuración aplicada[/green]")
        
        console.print(f"\n[bold green]✅ Perfil '{profile.name}' activado[/bold green]")
        
        # Mostrar configuración aplicada
        current = get_current_dns()
        if current:
            _show_dns_table(current, console)
        
        # Validar DNS
        if typer.confirm("\n¿Deseas validar que el DNS funciona?", default=True):
            test_dns(console)
    except PermissionError:
        console.print("\n[red]❌ Se requieren permisos de root para modificar DNS[/red]")
        console.print(f"[yellow]Ejecuta con sudo: sudo lsxtool network dns enable {profile_name}[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Error al activar perfil: {e}[/red]")
        sys.exit(1)


@dns_app.command()
def remove(
    profile_name: str = typer.Argument(..., help="Nombre del perfil DNS a eliminar")
):
    """
    Elimina un perfil DNS (no elimina el perfil activo)
    
    Requiere confirmación antes de eliminar.
    """
    console.print(Panel.fit(f"[bold cyan]Eliminar Perfil DNS: {profile_name}[/bold cyan]", border_style="cyan"))
    
    profile = get_profile(profile_name)
    
    if not profile:
        console.print(f"[red]❌ Perfil '{profile_name}' no encontrado[/red]")
        sys.exit(1)
    
    # No permitir eliminar perfiles por defecto
    if profile_name.lower() in ["normal", "corp"]:
        console.print("[red]❌ No se pueden eliminar los perfiles por defecto (normal, corp)[/red]")
        sys.exit(1)
    
    from rich.prompt import Confirm
    if not Confirm.ask(f"\n¿Estás seguro de eliminar el perfil '{profile_name}'?", default=False):
        console.print("[yellow]Operación cancelada[/yellow]")
        return
    
    if remove_profile(profile_name):
        console.print(f"\n[green]✅ Perfil '{profile_name}' eliminado[/green]")
    else:
        console.print(f"\n[red]❌ Error al eliminar perfil[/red]")
        sys.exit(1)


@dns_app.command()
def status():
    """
    Muestra el perfil DNS activo y su estado
    
    Indica qué perfil está aplicado y valida la resolución actual.
    """
    console.print(Panel.fit("[bold cyan]Estado de Configuración DNS[/bold cyan]", border_style="cyan"))
    
    current = get_current_dns()
    
    if not current:
        console.print("[yellow]⚠️ No se pudo leer la configuración DNS actual[/yellow]")
        return
    
    _show_dns_table(current, console)
    
    # Detectar modo actual
    current_servers = [s.strip() for s in current.servers]
    normal_servers = DNS_NORMAL.servers
    corp_servers = DNS_CORPORATIVO.servers
    
    mode = None
    if set(current_servers) == set(normal_servers):
        mode = "[green]Normal/Público[/green]"
    elif set(current_servers) == set(corp_servers):
        mode = "[yellow]Corporativo[/yellow]"
    else:
        mode = "[dim]Personalizado[/dim]"
    
    console.print(f"\n[bold]Modo actual:[/bold] {mode}")


@dns_app.command()
def test(
    host: Optional[str] = typer.Option(None, "--host", "-h", help="Host a probar (por defecto: google.com)")
):
    """
    Valida la resolución DNS del perfil activo
    
    Prueba conectividad con los servidores DNS configurados.
    """
    console.print(Panel.fit("[bold cyan]Validación de DNS[/bold cyan]", border_style="cyan"))
    
    test_host = host or "google.com"
    
    # Mostrar configuración actual antes de probar
    current = get_current_dns()
    if current:
        console.print(f"\n[dim]Configuración actual:[/dim]")
        console.print(f"[dim]Servidores: {', '.join(current.servers)}[/dim]\n")
    
    test_dns(console, test_host)


@dns_app.command("restore", hidden=True)
def restore():
    """
    Restaura la configuración DNS desde el backup (si existe)
    
    Comando oculto para compatibilidad con versiones anteriores.
    """
    from .dns_manager import RESOLV_CONF_BACKUP, RESOLV_CONF
    
    console.print(Panel.fit("[bold cyan]Restaurar Configuración DNS[/bold cyan]", border_style="cyan"))
    
    if not RESOLV_CONF_BACKUP.exists():
        console.print("[yellow]⚠️ No se encontró backup de configuración DNS[/yellow]")
        console.print("[dim]No hay configuración previa para restaurar[/dim]")
        return
    
    try:
        import shutil
        
        # Verificar permisos
        if os.geteuid() != 0:
            raise PermissionError("Se requieren permisos de root para restaurar DNS")
        
        # Restaurar backup
        shutil.copy2(RESOLV_CONF_BACKUP, RESOLV_CONF)
        os.chmod(RESOLV_CONF, 0o644)
        
        console.print("[green]✅ Configuración DNS restaurada desde backup[/green]")
        
        # Mostrar configuración restaurada
        current = get_current_dns()
        if current:
            _show_dns_table(current, console)
    except PermissionError:
        console.print("\n[red]❌ Se requieren permisos de root para restaurar DNS[/red]")
        console.print("[yellow]Ejecuta con sudo: sudo lsxtool networks restore[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Error al restaurar DNS: {e}[/red]")
        sys.exit(1)


def _show_dns_table(dns_config: DNSConfig, console: Console):
    """Muestra la configuración DNS en una tabla"""
    table = Table(title="Configuración DNS Actual", show_header=True, header_style="bold cyan")
    table.add_column("Campo", style="cyan", width=20)
    table.add_column("Valor", style="green")
    
    table.add_row("Modo", dns_config.name)
    table.add_row("Descripción", dns_config.description)
    
    servers_text = "\n".join([f"  • {s}" for s in dns_config.servers])
    table.add_row("Servidores DNS", servers_text)
    
    if dns_config.search_domains:
        search_text = "\n".join([f"  • {d}" for d in dns_config.search_domains])
        table.add_row("Dominios de búsqueda", search_text)
    
    console.print(table)
