"""
Módulo para crear archivos de configuración (.conf) cuando no existen
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Literal
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt

from ..cli_modules.config_generators import generate_nginx_config, generate_apache_config


def create_conf_file(
    domain: str,
    backend_type: Optional[str],
    base_dir: Path,
    console: Console,
    target: Optional[str] = None
) -> Optional[Path]:
    """
    Crea un archivo .conf y configuración Traefik para un dominio cuando no existe
    
    Args:
        domain: Dominio del sitio
        backend_type: Tipo de backend inferido (puede ser None para preguntar)
        base_dir: Directorio base del proyecto
        console: Console de Rich para salida
        target: Target del backend (ej: 'localhost:9100')
    
    Returns:
        Path del archivo .conf creado o None si se canceló
    """
    # Importar catálogos
    from .catalogs import (
        get_backends,
        get_backend_port,
        get_backend_versions,
        get_providers,
        get_environments,
        get_service_types
    )
    
    # Preguntar por el backend desde catálogo (con versión)
    backends_list = get_backends()
    
    console.print("\n[bold cyan]Selecciona el servidor web (backend):[/bold cyan]")
    backend_options = []
    for idx, backend in enumerate(backends_list, 1):
        port = get_backend_port(backend)
        versions = get_backend_versions(backend)
        port_str = f" (puerto {port})" if port else ""
        version_str = f" - Versión disponible: {versions[0]}" if versions else ""
        console.print(f"  [cyan]{idx}.[/cyan] {backend.upper()}{port_str}{version_str}")
        backend_options.append(backend)
    
    backend_choice = Prompt.ask(
        "\n[bold]Selecciona Servidor Web[/bold]",
        choices=[str(i) for i in range(1, len(backends_list) + 1)],
        default=str(1) if backends_list else None
    )
    
    selected_backend = backend_options[int(backend_choice) - 1] if backend_choice else None
    
    if not selected_backend:
        console.print("[red]❌ Servidor web no seleccionado[/red]")
        return None
    
    # Obtener puerto estándar del catálogo
    standard_port = get_backend_port(selected_backend)
    if not standard_port:
        console.print(f"[red]❌ No se encontró puerto estándar para {selected_backend}[/red]")
        return None
    
    # Preguntar versión del servidor web
    backend_versions = get_backend_versions(selected_backend)
    if backend_versions:
        console.print(f"\n[bold cyan]Versión de {selected_backend.upper()}:[/bold cyan]")
        for idx, version in enumerate(backend_versions, 1):
            console.print(f"  [cyan]{idx}.[/cyan] {version}")
        
        version_choice = Prompt.ask(
            f"\n[bold]Selecciona versión de {selected_backend.upper()}[/bold]",
            choices=[str(i) for i in range(1, len(backend_versions) + 1)],
            default="1"
        )
        backend_version = backend_versions[int(version_choice) - 1]
    else:
        backend_version = None
        console.print(f"[yellow]⚠️  No se detectó versión de {selected_backend}[/yellow]")
    
    # Preguntar proveedor
    providers_list = get_providers()
    console.print("\n[bold cyan]Proveedores disponibles:[/bold cyan]")
    for idx, provider in enumerate(providers_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {provider}")
    
    provider_choice = Prompt.ask(
        "\n[bold]Selecciona Proveedor[/bold]",
        choices=[str(i) for i in range(1, len(providers_list) + 1)],
        default="1"
    )
    selected_provider = providers_list[int(provider_choice) - 1]
    
    # Preguntar environment
    environments_list = get_environments()
    console.print("\n[bold cyan]Ambientes disponibles:[/bold cyan]")
    for idx, env in enumerate(environments_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {env.upper()}")
    
    environment_choice = Prompt.ask(
        "\n[bold]Selecciona Ambiente[/bold]",
        choices=[str(i) for i in range(1, len(environments_list) + 1)],
        default="1"
    )
    selected_environment = environments_list[int(environment_choice) - 1]
    
    # Preguntar tipo de servicio
    service_types_list = get_service_types()
    console.print("\n[bold cyan]Tipos de servicio disponibles:[/bold cyan]")
    for idx, st in enumerate(service_types_list, 1):
        console.print(f"  [cyan]{idx}.[/cyan] {st.upper()}")
    
    service_type_choice = Prompt.ask(
        "\n[bold]Selecciona Tipo de Servicio[/bold]",
        choices=[str(i) for i in range(1, len(service_types_list) + 1)],
        default="1"
    )
    selected_service_type = service_types_list[int(service_type_choice) - 1]
    
    # Preguntar tecnología
    console.print("\n[bold cyan]Tecnología de la aplicación:[/bold cyan]")
    console.print("1. PHP")
    console.print("2. Node.js")
    console.print("3. Python")
    console.print("4. HTML estático")
    console.print("5. React/Vue/Angular (SPA)")
    
    tech_choice = Prompt.ask(
        "\n[bold]Selecciona Tecnología[/bold]",
        choices=["1", "2", "3", "4", "5"],
        default="1"
    )
    
    tech_types = {
        "1": "php",
        "2": "node",
        "3": "python",
        "4": "html",
        "5": "spa"
    }
    selected_tech = tech_types[tech_choice]
    
    # Preguntar versión de la tecnología
    tech_version = None
    from .tech_versions import get_php_versions, get_node_versions, get_python_versions
    
    if selected_tech == "php":
        php_versions = get_php_versions()
        if php_versions:
            console.print("\n[bold cyan]Versiones de PHP disponibles:[/bold cyan]")
            for idx, version in enumerate(php_versions, 1):
                console.print(f"  [cyan]{idx}.[/cyan] PHP {version}")
            
            version_choice = Prompt.ask(
                "\n[bold]Selecciona versión de PHP[/bold]",
                choices=[str(i) for i in range(1, len(php_versions) + 1)],
                default="1"
            )
            tech_version = php_versions[int(version_choice) - 1]
        else:
            console.print("[yellow]⚠️  No se detectaron versiones de PHP, usando valores por defecto[/yellow]")
            tech_version = Prompt.ask(
                "Versión de PHP-FPM",
                choices=["7.2", "7.4", "8.0", "8.1", "8.2", "8.3", "8.4"],
                default="8.2"
            )
    elif selected_tech == "node":
        node_versions = get_node_versions()
        if node_versions:
            console.print("\n[bold cyan]Versiones de Node.js disponibles:[/bold cyan]")
            for idx, version in enumerate(node_versions, 1):
                console.print(f"  [cyan]{idx}.[/cyan] Node.js {version}")
            
            version_choice = Prompt.ask(
                "\n[bold]Selecciona versión de Node.js[/bold]",
                choices=[str(i) for i in range(1, len(node_versions) + 1)],
                default="1"
            )
            tech_version = node_versions[int(version_choice) - 1]
        else:
            tech_version = Prompt.ask("Versión de Node.js", default="20.x")
    elif selected_tech == "python":
        python_versions = get_python_versions()
        if python_versions:
            console.print("\n[bold cyan]Versiones de Python disponibles:[/bold cyan]")
            for idx, version in enumerate(python_versions, 1):
                console.print(f"  [cyan]{idx}.[/cyan] Python {version}")
            
            version_choice = Prompt.ask(
                "\n[bold]Selecciona versión de Python[/bold]",
                choices=[str(i) for i in range(1, len(python_versions) + 1)],
                default="1"
            )
            tech_version = python_versions[int(version_choice) - 1]
        else:
            tech_version = Prompt.ask("Versión de Python", default="3.11")
    
    # Preguntar tipo de aplicación (framework específico si es PHP)
    app_type = None
    if selected_tech == "php":
        console.print("\n[bold]Framework PHP:[/bold]")
        console.print("1. PHP simple")
        console.print("2. Laravel")
        console.print("3. Phalcon")
        
        app_type_choice = Prompt.ask(
            "Selecciona el framework",
            choices=["1", "2", "3"],
            default="1"
        )
        
        app_types = {
            "1": "php",
            "2": "laravel",
            "3": "phalcon"
        }
        app_type = app_types[app_type_choice]
    elif selected_tech in ("node", "python"):
        app_type = "proxy"  # Para Node/Python usamos proxy reverso
    elif selected_tech == "html":
        app_type = "html"
    elif selected_tech == "spa":
        app_type = "spa"
    
    # Preguntar ruta del proyecto
    root_path = Prompt.ask(
        "Ruta del directorio raíz del proyecto",
        default=f"/var/www/{domain.split('.')[0]}"
    )
    
    # Ajustar ruta según tipo de aplicación
    if app_type == "laravel":
        root_path_actual = root_path
        root_path = f"{root_path}/public"
        console.print(f"[yellow]⚠ Laravel detectado - DocumentRoot será: {root_path}[/yellow]")
    
    # Si es proxy (Node/Python), preguntar puerto destino
    proxy_port = None
    if app_type == "proxy":
        proxy_port = IntPrompt.ask(
            "Puerto de la aplicación destino",
            default=3000
        )
    
    # php_version ahora viene de tech_version
    php_version = tech_version if selected_tech == "php" else None
    
    # Generar configuración de Traefik primero
    from ..cli_modules.config_generators import generate_traefik_config
    
    traefik_config_dir = base_dir / "lsxtool" / "servers" / "traefik" / "config" / "dynamic" / "http"
    traefik_config_file = traefik_config_dir / f"{domain}.yml"
    
    traefik_config = generate_traefik_config(domain, selected_backend, standard_port)
    
    try:
        traefik_config_dir.mkdir(parents=True, exist_ok=True)
        traefik_config_file.write_text(traefik_config)
        console.print(f"[green]✅ Configuración Traefik creada: {traefik_config_file}[/green]")
    except Exception as e:
        console.print(f"[red]❌ Error al crear configuración Traefik: {e}[/red]")
        return None
    
    # Determinar ruta del archivo .conf usando proveedor y environment
    if selected_backend.lower() == "nginx":
        # Buscar estructura de directorios de Nginx
        nginx_base = base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d"
        
        # Usar proveedor y environment para determinar la ruta
        provider_lower = selected_provider.lower()
        if provider_lower == "lsx":
            provider_dir = "lunarsystemx"
        elif provider_lower == "stic":
            provider_dir = "stic"
        else:
            provider_dir = "stic"  # Default
        
        conf_dir = nginx_base / provider_dir / selected_environment
        conf_path = conf_dir / f"{domain}.conf"
        
        # Generar configuración de Nginx
        if app_type == "proxy":
            # Generar configuración de proxy para Nginx
            config = _generate_nginx_proxy_config(domain, proxy_port, standard_port)
        else:
            config = generate_nginx_config(domain, root_path, app_type, php_version, standard_port)
    else:  # Apache
        apache_base = base_dir / "lsxtool" / "servers" / "apache" / "configuration" / "etc" / "apache2" / "sites-available"
        # Usar environment para determinar la ruta
        conf_dir = apache_base / selected_environment
        conf_path = conf_dir / f"{domain}.conf"
        
        # Generar configuración de Apache
        # Nota: Apache no soporta proxy reverso directamente en este contexto
        # Si se necesita proxy, usar Nginx
        if app_type == "proxy":
            console.print("[yellow]⚠️  Apache no soporta proxy reverso en esta configuración[/yellow]")
            console.print("[yellow]   Considera usar Nginx para proxy reverso[/yellow]")
            return None
        
        config = generate_apache_config(domain, root_path, app_type, php_version)
    
    # Crear directorio si no existe
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Escribir archivo .conf
    try:
        conf_path.write_text(config)
        console.print(f"[green]✅ Archivo .conf creado: {conf_path}[/green]")
        
        # Escribir metadatos en el archivo .conf
        from .meta_parser import write_meta_to_conf
        
        meta = {
            "provider": selected_provider,
            "environment": selected_environment,
            "service_type": selected_service_type,
            "backend": selected_backend,
            "backend_version": backend_version,
            "tech": selected_tech.lower() if selected_tech else None,
            "tech_version": tech_version if tech_version else None
        }
        
        write_meta_to_conf(conf_path, meta, console)
        
        # Resumen
        console.print(f"\n[bold cyan]Resumen:[/bold cyan]")
        console.print(f"  Proveedor: {selected_provider}")
        console.print(f"  Ambiente: {selected_environment.upper()}")
        console.print(f"  Tipo de Servicio: {selected_service_type.upper()}")
        console.print(f"  Servidor Web: {selected_backend.upper()} {backend_version or 'N/A'}")
        console.print(f"  Tecnología: {selected_tech.upper()} {tech_version or 'N/A'}")
        console.print(f"  Puerto: {standard_port}")
        console.print(f"  Traefik YAML: {traefik_config_file}")
        console.print(f"  Archivo .conf: {conf_path}")
        
        return conf_path
    except Exception as e:
        console.print(f"[red]❌ Error al crear archivo .conf: {e}[/red]")
        return None


def _generate_nginx_proxy_config(domain: str, proxy_port: int, listen_port: int) -> str:
    """Genera configuración de Nginx para proxy reverso"""
    site_name = domain.replace('.', '-')
    
    config = f"""# Configuración para {domain} - Proxy Reverso
# Traefik enruta a Nginx en puerto {listen_port}
# Aplicación destino corre en puerto {proxy_port}
# ENTORNO: DEV (sin SSL, Traefik maneja SSL en PROD)

server {{
    listen {listen_port};
    listen [::]:{listen_port};
    server_name {domain};

    # ========== LOGS ==========
    access_log /var/log/nginx/{site_name}-access.log;
    error_log /var/log/nginx/{site_name}-error.log;

    # ========== PROXY A APLICACIÓN ==========
    location / {{
        # Proxy a aplicación
        proxy_pass http://127.0.0.1:{proxy_port};
        proxy_http_version 1.1;
        
        # Headers estándar para proxy
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Headers adicionales para Traefik
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        
        # Buffers optimizados
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }}
}}
"""
    return config


def update_hosts_file(domain: str, console: Console, ip: str = "127.0.0.1") -> bool:
    """
    Modifica el archivo /etc/hosts para apuntar un dominio a localhost
    
    Args:
        domain: Dominio a agregar
        console: Console de Rich para salida
        ip: IP a la que apuntar (default: 127.0.0.1)
    
    Returns:
        True si se modificó exitosamente, False en caso contrario
    """
    hosts_file = Path("/etc/hosts")
    
    if not hosts_file.exists():
        console.print("[red]❌ Archivo /etc/hosts no encontrado[/red]")
        return False
    
    # Verificar permisos
    if os.geteuid() != 0:
        console.print("[yellow]⚠️  Se requieren permisos de root para modificar /etc/hosts[/yellow]")
        console.print("[cyan]💡 Puedes agregarlo manualmente ejecutando:[/cyan]")
        console.print(f"[cyan]   echo '{ip}\\t{domain}' | sudo tee -a /etc/hosts[/cyan]")
        return False
    
    try:
        # Leer contenido actual
        content = hosts_file.read_text()
        lines = content.split('\n')
        
        # Verificar si ya existe
        domain_exists = False
        for i, line in enumerate(lines):
            if domain in line and not line.strip().startswith('#'):
                domain_exists = True
                # Actualizar línea existente
                lines[i] = f"{ip}\t{domain}"
                console.print(f"[yellow]⚠️  Dominio ya existe en hosts, actualizando...[/yellow]")
                break
        
        # Si no existe, agregar al final
        if not domain_exists:
            lines.append(f"{ip}\t{domain}")
            console.print(f"[green]✅ Agregando {domain} a /etc/hosts[/green]")
        
        # Escribir archivo
        hosts_file.write_text('\n'.join(lines) + '\n')
        console.print(f"[green]✅ Archivo /etc/hosts actualizado: {domain} -> {ip}[/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Error al modificar /etc/hosts: {e}[/red]")
        return False
