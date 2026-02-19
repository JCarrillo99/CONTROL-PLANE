"""
Módulo para gestión de DNS en WSL
Maneja la configuración de /etc/resolv.conf de forma segura
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass
class DNSConfig:
    """Configuración DNS"""
    name: str
    servers: List[str]
    description: str
    search_domains: Optional[List[str]] = None


RESOLV_CONF = Path("/etc/resolv.conf")
RESOLV_CONF_BACKUP = Path("/etc/resolv.conf.backup")


def _check_permissions() -> None:
    """Verifica que se tengan permisos de root"""
    if os.geteuid() != 0:
        raise PermissionError("Se requieren permisos de root para modificar DNS")


def _backup_resolv_conf() -> None:
    """Crea un backup de /etc/resolv.conf"""
    if RESOLV_CONF.exists():
        shutil.copy2(RESOLV_CONF, RESOLV_CONF_BACKUP)
        # Cambiar permisos del backup
        os.chmod(RESOLV_CONF_BACKUP, 0o644)


def write_resolv_conf(config: DNSConfig) -> None:
    """
    Escribe la configuración DNS en /etc/resolv.conf
    En WSL, este archivo puede ser sobrescrito automáticamente
    """
    _check_permissions()
    _backup_resolv_conf()
    
    # Generar contenido del archivo
    lines = [
        "# Configuración DNS generada por LSX Tool (networks)",
        f"# Modo: {config.name}",
        f"# {config.description}",
        "# Generado automáticamente - NO EDITAR MANUALMENTE",
        ""
    ]
    
    # Agregar servidores DNS
    for server in config.servers:
        lines.append(f"nameserver {server}")
    
    # Agregar dominios de búsqueda si existen
    if config.search_domains:
        lines.append("")
        search_line = " ".join(config.search_domains)
        lines.append(f"search {search_line}")
    
    # Escribir archivo
    content = "\n".join(lines) + "\n"
    
    try:
        RESOLV_CONF.write_text(content)
        # Asegurar permisos correctos
        os.chmod(RESOLV_CONF, 0o644)
    except Exception as e:
        # Restaurar backup si falla
        if RESOLV_CONF_BACKUP.exists():
            shutil.copy2(RESOLV_CONF_BACKUP, RESOLV_CONF)
        raise Exception(f"Error al escribir /etc/resolv.conf: {e}")


def get_current_dns() -> Optional[DNSConfig]:
    """
    Lee la configuración DNS actual de /etc/resolv.conf
    """
    if not RESOLV_CONF.exists():
        return None
    
    try:
        content = RESOLV_CONF.read_text()
        lines = content.split("\n")
        
        servers = []
        search_domains = []
        description = "Configuración actual"
        
        for line in lines:
            line = line.strip()
            
            # Ignorar comentarios y líneas vacías
            if not line or line.startswith("#"):
                # Buscar descripción en comentarios
                if "Modo:" in line:
                    description = line.split("Modo:")[-1].strip()
                continue
            
            # Parsear nameserver
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    servers.append(parts[1])
            
            # Parsear search
            if line.startswith("search"):
                parts = line.split()
                if len(parts) >= 2:
                    search_domains = parts[1:]
        
        if not servers:
            return None
        
        return DNSConfig(
            name=description,
            servers=servers,
            description=description,
            search_domains=search_domains if search_domains else None
        )
    except Exception:
        return None


def set_dns_normal(config: DNSConfig, console: Console) -> None:
    """
    Configura DNS en modo Normal/Público
    """
    console.print(f"\n[cyan]Configurando DNS: {config.name}[/cyan]")
    console.print(f"[dim]Servidores: {', '.join(config.servers)}[/dim]")
    
    write_resolv_conf(config)
    
    console.print("[green]✓ Configuración aplicada[/green]")


def set_dns_corporativo(config: DNSConfig, console: Console) -> None:
    """
    Configura DNS en modo Corporativo
    """
    console.print(f"\n[cyan]Configurando DNS: {config.name}[/cyan]")
    console.print(f"[dim]Servidores: {', '.join(config.servers)}[/dim]")
    
    write_resolv_conf(config)
    
    console.print("[green]✓ Configuración aplicada[/green]")


def test_dns(console: Console, host: str = "google.com") -> None:
    """
    Valida que el DNS configurado funciona correctamente
    """
    console.print(f"\n[yellow]Validando DNS con host: {host}[/yellow]")
    
    # Obtener configuración actual
    current = get_current_dns()
    if not current or not current.servers:
        console.print("[red]❌ No se pudo obtener la configuración DNS actual[/red]")
        return
    
    # Probar cada servidor DNS
    table = Table(title="Resultados de Validación DNS", show_header=True, header_style="bold cyan")
    table.add_column("Servidor DNS", style="cyan")
    table.add_column("Estado", style="green")
    table.add_column("Tiempo de respuesta", style="yellow")
    
    working_count = 0
    total_count = len(current.servers)
    
    for server in current.servers:
        console.print(f"[dim]Probando {server}...[/dim]", end=" ")
        
        # Usar nslookup o dig para validar
        try:
            # Intentar con nslookup primero
            result = subprocess.run(
                ["nslookup", host, server],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            
            if result.returncode == 0:
                # Extraer tiempo de respuesta si está disponible
                output = result.stdout
                status = "[green]✅ Funcional[/green]"
                response_time = "[dim]N/A[/dim]"
                
                # Intentar ping para obtener tiempo de respuesta
                ping_result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", server],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False
                )
                
                if ping_result.returncode == 0:
                    # Extraer tiempo del ping
                    for line in ping_result.stdout.split("\n"):
                        if "time=" in line:
                            try:
                                time_str = line.split("time=")[1].split()[0]
                                response_time = f"[green]{time_str}[/green]"
                            except:
                                pass
                
                table.add_row(server, status, response_time)
                working_count += 1
                console.print(f"[green]✓[/green]")
            else:
                # Intentar con dig como alternativa
                dig_result = subprocess.run(
                    ["dig", f"@{server}", host, "+short", "+timeout=3"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                
                if dig_result.returncode == 0 and dig_result.stdout.strip():
                    status = "[green]✅ Funcional[/green]"
                    response_time = "[dim]N/A[/dim]"
                    table.add_row(server, status, response_time)
                    working_count += 1
                    console.print(f"[green]✓[/green]")
                else:
                    status = "[red]❌ No responde[/red]"
                    response_time = "[red]Timeout[/red]"
                    table.add_row(server, status, response_time)
                    console.print(f"[red]✗[/red]")
                    continue
        except subprocess.TimeoutExpired:
            status = "[red]❌ Timeout[/red]"
            response_time = "[red]>5s[/red]"
            table.add_row(server, status, response_time)
            console.print(f"[red]✗[/red]")
        except FileNotFoundError:
            # nslookup/dig no disponibles, intentar con ping
            try:
                ping_result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", server],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False
                )
                
                if ping_result.returncode == 0:
                    status = "[yellow]⚠️ Responde (ping)[/yellow]"
                    response_time = "[dim]N/A[/dim]"
                    table.add_row(server, status, response_time)
                    working_count += 1
                    console.print(f"[yellow]⚠[/yellow]")
                else:
                    status = "[red]❌ No responde[/red]"
                    response_time = "[red]N/A[/red]"
                    table.add_row(server, status, response_time)
                    console.print(f"[red]✗[/red]")
            except Exception:
                status = "[red]❌ Error al probar[/red]"
                response_time = "[red]N/A[/red]"
                table.add_row(server, status, response_time)
                console.print(f"[red]✗[/red]")
        except Exception as e:
            status = f"[red]❌ Error: {str(e)[:30]}[/red]"
            response_time = "[red]N/A[/red]"
            table.add_row(server, status, response_time)
            console.print(f"[red]✗[/red]")
    
    console.print()
    console.print(table)
    
    # Mostrar mensaje según resultados
    if working_count == total_count:
        console.print(f"\n[bold green]✅ DNS configurado correctamente - Todos los servidores funcionando ({working_count}/{total_count})[/bold green]")
    elif working_count > 0:
        console.print(f"\n[yellow]⚠️ DNS parcialmente funcional - {working_count} de {total_count} servidores responden[/yellow]")
        console.print("[dim]El sistema usará los servidores que funcionan. Considera revisar los servidores que no responden.[/dim]")
    else:
        console.print("\n[bold red]❌ Ningún servidor DNS responde[/bold red]")
        console.print("[yellow]Verifica la configuración de red o contacta al departamento de Redes[/yellow]")


# Configuraciones DNS predefinidas
DNS_NORMAL = DNSConfig(
    name="Normal/Público",
    servers=["8.8.8.8", "1.1.1.1"],
    description="Google DNS y Cloudflare DNS"
)

DNS_CORPORATIVO = DNSConfig(
    name="Corporativo",
    servers=["192.168.25.19", "192.168.25.20"],
    description="DNS internos de la red corporativa"
)
