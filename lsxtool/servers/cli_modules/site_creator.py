"""
Módulo para crear nuevos sitios web
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Literal
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table

from .config_generators import (
    generate_traefik_config,
    generate_apache_config,
    generate_nginx_config
)


def create_site(
    domain: Optional[str],
    web_server: Optional[Literal["apache", "nginx"]],
    base_dir: Path,
    console: Console
):
    """
    Crea un nuevo sitio web con todas las configuraciones necesarias
    """
    console.print(Panel.fit("[bold cyan]Crear Nuevo Sitio Web[/bold cyan]", border_style="cyan"))
    
    # Verificar permisos de root
    if os.geteuid() != 0:
        console.print("[red]❌ Se requieren permisos de root para crear sitios[/red]")
        console.print("[yellow]Ejecuta con sudo: sudo python3 cli.py create[/yellow]")
        return
    
    # Paso 1: Dominio
    if not domain:
        domain = Prompt.ask("Ingresa el dominio", default="")
    
    if not domain:
        console.print("[red]❌ El dominio es requerido[/red]")
        return
    
    # Paso 2: Servidor web (Apache o Nginx)
    if not web_server:
        console.print("\n[bold]Selecciona el servidor web backend:[/bold]")
        console.print("1. Apache (puerto 9200)")
        console.print("2. Nginx (puerto 9100)")
        
        choice = Prompt.ask("Selecciona una opción", choices=["1", "2"], default="1")
        web_server = "apache" if choice == "1" else "nginx"
    
    console.print(f"[green]✓ Servidor web: {web_server}[/green]")
    
    # Paso 3: Tipo de aplicación
    console.print("\n[bold]Tipo de aplicación:[/bold]")
    console.print("1. PHP (simple)")
    console.print("2. Laravel")
    console.print("3. Phalcon")
    console.print("4. HTML estático")
    console.print("5. React/Vue/Angular (SPA)")
    
    app_type_choice = Prompt.ask("Selecciona el tipo", choices=["1", "2", "3", "4", "5"], default="1")
    
    app_types = {
        "1": "php",
        "2": "laravel",
        "3": "phalcon",
        "4": "html",
        "5": "spa"
    }
    app_type = app_types[app_type_choice]
    
    # Paso 4: Ruta del proyecto
    root_path = Prompt.ask(
        "Ruta del directorio raíz del proyecto",
        default=f"/mnt/d/www/01-STIC/web/{domain.split('.')[0]}"
    )
    
    # Ajustar ruta según tipo de aplicación
    if app_type == "laravel":
        # Laravel usa /public como raíz
        root_path_actual = root_path
        root_path = f"{root_path}/public"
        console.print(f"[yellow]⚠ Laravel detectado - DocumentRoot será: {root_path}[/yellow]")
    
    # Paso 5: Versión de PHP (si aplica)
    php_version = None
    if app_type in ("php", "laravel", "phalcon"):
        php_version = Prompt.ask(
            "Versión de PHP-FPM",
            choices=["7.2", "7.4", "8.0", "8.1", "8.2", "8.3", "8.4"],
            default="8.2"
        )
    
    # Paso 5.5: Metadatos del sitio
    console.print("\n[bold]Metadatos del sitio:[/bold]")
    owner = Prompt.ask("Owner/Equipo responsable", default="")
    provider = Prompt.ask("Proveedor", choices=["STIC", "LSX", "EXTERNAL"], default="STIC")
    service_type = Prompt.ask("Tipo de servicio", choices=["web", "api", "admin", "static"], default="web")
    environment = Prompt.ask("Ambiente", choices=["dev", "qa", "prod"], default="dev")
    
    # Versión del backend (servidor web)
    if web_server == "apache":
        backend_version = Prompt.ask("Versión de Apache", default="2.4")
    else:
        backend_version = Prompt.ask("Versión de Nginx", default="1.18")
    
    # Paso 6: Puerto del servidor web
    if web_server == "apache":
        web_port = 9200
    else:
        web_port = 9100
    
    # Resumen
    console.print("\n[bold cyan]Resumen de configuración:[/bold cyan]")
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Campo", style="cyan")
    summary_table.add_column("Valor", style="green")
    
    summary_table.add_row("Dominio", domain)
    summary_table.add_row("Servidor Web", web_server)
    summary_table.add_row("Tipo de App", app_type)
    summary_table.add_row("Ruta Raíz", root_path)
    if php_version:
        summary_table.add_row("PHP Version", php_version)
    summary_table.add_row("Puerto Backend", str(web_port))
    
    console.print(summary_table)
    
    if not Confirm.ask("\n¿Continuar con la creación?", default=True):
        console.print("[yellow]Operación cancelada[/yellow]")
        return
    
    # Generar configuraciones
    console.print("\n[cyan]Generando configuraciones...[/cyan]")
    
    # Generar configuración de Traefik (siempre)
    # base_dir ahora apunta a lsxtool/servers/
    traefik_config_path = base_dir / "traefik" / "config" / "dynamic" / "http" / f"{domain}.yml"
    traefik_config = generate_traefik_config(domain, web_server, web_port)
    
    try:
        traefik_config_path.parent.mkdir(parents=True, exist_ok=True)
        traefik_config_path.write_text(traefik_config)
        console.print(f"[green]✅ Configuración Traefik creada: {traefik_config_path}[/green]")
    except Exception as e:
        console.print(f"[red]❌ Error al crear configuración Traefik: {e}[/red]")
        return
    
    # Generar configuración del servidor web
    if web_server == "apache":
        apache_config_path = base_dir / "apache" / "configuration" / "etc" / "apache2" / "sites-available" / "dev" / f"{domain}.conf"
        apache_config = generate_apache_config(domain, root_path, app_type, php_version)
        
        try:
            apache_config_path.parent.mkdir(parents=True, exist_ok=True)
            apache_config_path.write_text(apache_config)
            console.print(f"[green]✅ Configuración Apache creada: {apache_config_path}[/green]")
            
            # Escribir metadatos en el archivo .conf
            meta = {
                "owner": owner,
                "provider": provider,
                "service_type": service_type,
                "environment": environment,
                "backend": "apache",
                "backend_version": backend_version,
                "tech": app_type if app_type in ("php", "laravel", "phalcon") else None,
                "tech_version": php_version if php_version else None
            }
            
            from ..sites.meta_parser import write_meta_to_conf, validate_meta
            is_valid, warnings = validate_meta(meta, console)
            write_meta_to_conf(apache_config_path, meta, console)
            
        except Exception as e:
            console.print(f"[red]❌ Error al crear configuración Apache: {e}[/red]")
            return
    else:
        nginx_config_path = base_dir / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / "stic" / f"{domain}.conf"
        nginx_config = generate_nginx_config(domain, root_path, app_type, php_version, web_port)
        
        try:
            nginx_config_path.parent.mkdir(parents=True, exist_ok=True)
            nginx_config_path.write_text(nginx_config)
            console.print(f"[green]✅ Configuración Nginx creada: {nginx_config_path}[/green]")
            
            # Escribir metadatos en el archivo .conf
            meta = {
                "owner": owner,
                "provider": provider,
                "service_type": service_type,
                "environment": environment,
                "backend": "nginx",
                "backend_version": backend_version,
                "tech": app_type if app_type in ("php", "laravel", "phalcon") else None,
                "tech_version": php_version if php_version else None
            }
            
            from ..sites.meta_parser import write_meta_to_conf, validate_meta
            is_valid, warnings = validate_meta(meta, console)
            write_meta_to_conf(nginx_config_path, meta, console)
            
        except Exception as e:
            console.print(f"[red]❌ Error al crear configuración Nginx: {e}[/red]")
            return
    
    # Preguntar si sincronizar ahora
    if Confirm.ask("\n¿Sincronizar configuraciones ahora?", default=True):
        console.print("\n[cyan]Sincronizando...[/cyan]")
        
        # Importar función de sincronización
        from .sync import sync_configs
        
        # Sincronizar Traefik y el servidor web seleccionado
        if web_server == "apache":
            sync_configs("apache", base_dir, console)
        else:
            sync_configs("nginx", base_dir, console)
        
        # Siempre sincronizar Traefik también
        sync_configs("traefik", base_dir, console)
        
        console.print("[green]✅ Configuraciones sincronizadas[/green]")
    
    console.print("\n[bold green]✅ Sitio creado exitosamente![/bold green]")
    console.print(f"[cyan]Dominio:[/cyan] {domain}")
    console.print(f"[cyan]Acceso:[/cyan] https://{domain}")
