"""
Módulo para sincronización de configuraciones.
- Modo interactivo (sin servicio): pregunta provider → servicio → ambiente → listado de servidores → sincroniza los elegidos.
- Modo legacy (traefik/apache/nginx/all): usa SYNC_ROUTES desde base_dir (comportamiento anterior).
"""

import os
import subprocess
import shutil
import yaml
from pathlib import Path
from typing import Optional, Literal

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .sync_routes import get_routes
from .server_config import list_configured_servers, get_workspace_dir


def sync_configs(
    service: Optional[Literal["traefik", "apache", "nginx", "all"]],
    base_dir: Path,
    console: Console,
):
    """
    Sincroniza configuraciones.
    - Si service es None: flujo interactivo por provider/servicio/ambiente/servidores configurados.
    - Si service está definido: modo legacy (SYNC_ROUTES para ese servicio).
    """
    if os.geteuid() != 0:
        console.print("[red]❌ Se requieren permisos de root para sincronizar[/red]")
        console.print("[yellow]💡 Ejecuta con: sudo lsxtool servers sync[/yellow]")
        return

    if service is None:
        _sync_interactive(base_dir, console)
        return

    # Modo legacy: por nombre de servicio
    sync_traefik = service in ("traefik", "all")
    sync_apache = service in ("apache", "all")
    sync_nginx = service in ("nginx", "all")
    if not (sync_traefik or sync_apache or sync_nginx):
        console.print("[yellow]Servicio no válido. Usa: traefik, apache, nginx o all[/yellow]")
        return
    if sync_traefik:
        _sync_service_by_routes(base_dir, "traefik", "Traefik", console)
        _reload_traefik(console)
    if sync_apache:
        _sync_service_by_routes(base_dir, "apache", "Apache", console)
        _apache_enable_dev_sites(console)
        _reload_apache(console)
    if sync_nginx:
        _sync_service_by_routes(base_dir, "nginx", "Nginx", console)
        _reload_nginx(console)
    console.print("\n[green]✅ Sincronización completada[/green]")


def _sync_interactive(base_dir: Path, console: Console) -> None:
    """Flujo: provider → servicio → ambiente → elegir servidor(es) → sincronizar."""
    servers = list_configured_servers()
    if not servers:
        console.print(Panel.fit("[bold cyan]Sincronización de Configuraciones[/bold cyan]", border_style="cyan"))
        console.print("[yellow]No hay servidores configurados (YAML en .lsxtool/providers/.../servers/).[/yellow]")
        console.print("[dim]Ejecuta 'lsxtool servers add' para dar de alta un servidor.[/dim]")
        return

    console.print(Panel.fit("[bold cyan]Sincronización de Configuraciones[/bold cyan]", border_style="cyan"))

    # Agrupar por provider
    providers = sorted({s["provider"] for s in servers})
    provider = providers[0] if len(providers) == 1 else _prompt_choice(
        console, "Provider", providers, lambda x: x
    )
    servers_p = [s for s in servers if s["provider"] == provider]

    # Por servicio
    services = sorted({s["service"] for s in servers_p})
    service = services[0] if len(services) == 1 else _prompt_choice(
        console, "Servicio", services, lambda x: x
    )
    servers_s = [s for s in servers_p if s["service"] == service]

    # Por ambiente
    envs = sorted({s["environment"] for s in servers_s})
    environment = envs[0] if len(envs) == 1 else _prompt_choice(
        console, "Ambiente", envs, lambda x: x
    )
    servers_e = [s for s in servers_s if s["environment"] == environment]

    # Listar servidores (nombre del YAML)
    table = Table(title=f"Servidores {provider} / {service} / {environment}", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Servidor", style="green")
    for i, s in enumerate(servers_e, 1):
        table.add_row(str(i), s["server_name"])
    console.print(table)
    choices = [str(i) for i in range(1, len(servers_e) + 1)]
    choice = Prompt.ask("¿Cuál sincronizar? (número o 'all' para todos)", default="all")
    if choice.strip().lower() == "all":
        selected = servers_e
    elif choice in choices:
        selected = [servers_e[int(choice) - 1]]
    else:
        console.print("[yellow]No se seleccionó ningún servidor.[/yellow]")
        return

    for s in selected:
        _sync_one_server(s, base_dir, console)
    console.print("\n[green]✅ Sincronización completada[/green]")


def _prompt_choice(console: Console, label: str, options: list, formatter):
    table = Table(title=label, show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Opción", style="green")
    for i, o in enumerate(options, 1):
        table.add_row(str(i), str(formatter(o)))
    console.print(table)
    c = Prompt.ask(f"Selecciona {label}", choices=[str(i) for i in range(1, len(options) + 1)], default="1")
    return options[int(c) - 1]


def _sync_one_server(server_info: dict, base_dir: Path, console: Console) -> None:
    """Sincroniza un servidor según su YAML (modo import: workspace→dest; managed: SYNC_ROUTES src→dest)."""
    path = server_info["yaml_path"]
    if not path.exists():
        console.print(f"[yellow]⚠ YAML no encontrado: {path}[/yellow]")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        console.print(f"[red]❌ Error leyendo {path}: {e}[/red]")
        return

    provider = server_info["provider"]
    service = server_info["service"]
    environment = server_info["environment"]
    server_name = server_info["server_name"]
    routes = config.get("routes") or []
    mode = config.get("mode", "managed")

    console.print(f"\n[cyan]🔄 {provider} / {service} / {environment} / {server_name}[/cyan]")

    if mode == "import":
        workspace_dir = get_workspace_dir(provider, service, environment, server_name)
        if not workspace_dir.exists():
            console.print(f"[yellow]  ⚠ Workspace no existe: {workspace_dir}[/yellow]")
            return
        for r in routes:
            src_path = workspace_dir / r.get("src", "")
            dest_path = Path(r["dest"])
            if not src_path.exists():
                console.print(f"[yellow]  ⚠ {r.get('label', r['src'])} no existe, omitido[/yellow]")
                continue
            try:
                if src_path.is_dir():
                    dest_path.mkdir(parents=True, exist_ok=True)
                    for f in src_path.rglob("*"):
                        if f.is_file():
                            rel = f.relative_to(src_path)
                            d = dest_path / rel
                            d.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(f, d)
                else:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                console.print(f"[green]  ✓[/green] {r.get('label', r['src'])} → {dest_path}")
            except Exception as e:
                console.print(f"[red]  ✗[/red] {r.get('label', r['src'])}: {e}")
    else:
        # managed/bootstrap: src relativo a base_dir (lsxtool/servers)
        for r in routes:
            src_path = base_dir / r.get("src", "")
            dest_path = Path(r["dest"])
            if not src_path.exists():
                console.print(f"[yellow]  ⚠ {r.get('label', r['src'])} no existe, omitido[/yellow]")
                continue
            chown = r.get("chown", "root:root")
            try:
                if src_path.is_file():
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                    _chown_chmod(dest_path, chown)
                else:
                    for f in src_path.rglob("*"):
                        if f.is_file():
                            rel = f.relative_to(src_path)
                            d = dest_path / rel
                            d.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(f, d)
                            _chown_chmod(d, chown)
                console.print(f"[green]  ✓[/green] {r.get('label', r['src'])} → {dest_path}")
            except Exception as e:
                console.print(f"[red]  ✗[/red] {r.get('label', r['src'])}: {e}")

    # Recarga si está definida en el YAML
    reload_cmd = (config.get("reload") or {}).get("cmd")
    if reload_cmd and service == "nginx":
        _reload_nginx(console)
    elif reload_cmd and service == "apache":
        _reload_apache(console)
    elif reload_cmd and service == "traefik":
        _reload_traefik(console)


def _sync_service_by_routes(
    base_dir: Path,
    service_id: str,
    service_name: str,
    console: Console,
) -> None:
    """Sincroniza un servicio usando el mapa de rutas declarativo."""
    console.print(f"\n[cyan]🔄 Sincronizando {service_name}...[/cyan]")
    routes = get_routes(service_id)
    for route in routes:
        src_path = base_dir / route["src"]
        dest_path = Path(route["dest"])
        label = route.get("label", route["src"])
        if not src_path.exists():
            console.print(f"[yellow]  ⚠️  ./{label} no existe, omitido[/yellow]")
            continue
        chown = route.get("chown", "root:root")
        route_type = route.get("type", "dir")
        glob_pattern = route.get("glob")
        try:
            if route_type == "file":
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest_path)
                _chown_chmod(dest_path, chown)
            else:
                # directorio: copiar árbol (respetando glob si existe)
                pattern = glob_pattern if glob_pattern else "*"
                copied = 0
                for f in src_path.rglob(pattern):
                    if not f.is_file():
                        continue
                    rel = f.relative_to(src_path)
                    dest_file = dest_path / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest_file)
                    _chown_chmod(dest_file, chown)
                    copied += 1
            console.print(f"[green]  ✓  ./{label}[/green] [dim]→[/dim] [green]{dest_path}[/green]")
        except Exception as e:
            console.print(f"[red]  ✗  ./{label} → {dest_path}: {e}[/red]")


def _chown_chmod(path: Path, chown: str) -> None:
    subprocess.run(["chown", chown, str(path)], check=False)
    subprocess.run(["chmod", "644", str(path)], check=False)


def _reload_traefik(console: Console) -> None:
    if subprocess.run(["systemctl", "is-active", "--quiet", "traefik"], check=False).returncode != 0:
        return
    r = subprocess.run(["systemctl", "reload", "traefik"], capture_output=True, text=True, check=False)
    if r.returncode == 0:
        console.print("[green]  ✓ Traefik recargado[/green]")
    else:
        r2 = subprocess.run(["systemctl", "restart", "traefik"], capture_output=True, text=True, check=False)
        if r2.returncode == 0:
            console.print("[green]  ✓ Traefik reiniciado[/green]")
        else:
            console.print("[yellow]  ⚠ No se pudo recargar/reiniciar Traefik[/yellow]")


def _apache_enable_dev_sites(console: Console) -> None:
    sites_avail = Path("/etc/apache2/sites-available")
    sites_enabled = Path("/etc/apache2/sites-enabled")
    dev_dir = sites_avail / "dev"
    if not dev_dir.exists():
        return
    for conf in dev_dir.glob("*.conf"):
        link = sites_enabled / conf.name
        if not link.exists():
            link.symlink_to(f"../sites-available/dev/{conf.name}")
            subprocess.run(["chown", "-h", "root:root", str(link)], check=False)


def _reload_apache(console: Console) -> None:
    r = subprocess.run(
        ["apache2ctl", "configtest"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0:
        _show_apache_errors(console, output)
        return
    if subprocess.run(["systemctl", "is-active", "--quiet", "apache2"], check=False).returncode != 0:
        return
    r2 = subprocess.run(["systemctl", "reload", "apache2"], capture_output=True, text=True, check=False)
    if r2.returncode == 0:
        console.print("[green]  ✓ Apache recargado[/green]")
    else:
        console.print("[yellow]  ⚠ No se pudo recargar Apache[/yellow]")


def _show_apache_errors(console: Console, output: str) -> None:
    console.print("[red]❌ Configuración de Apache tiene errores, no se recarga[/red]")
    for line in output.strip().split("\n")[:10]:
        line = line.replace("[", "\\[").replace("]", "\\]")
        console.print(f"[red]  {line}[/red]")
    console.print("[dim]Ejecuta 'apache2ctl configtest' para ver todos los errores[/dim]")


def _reload_nginx(console: Console) -> None:
    r = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0:
        console.print("[red]❌ Configuración de Nginx tiene errores, no se recarga[/red]")
        for line in output.strip().split("\n")[:10]:
            line = line.replace("[", "\\[").replace("]", "\\]")
            console.print(f"[red]  {line}[/red]")
        console.print("[dim]Ejecuta 'nginx -t' para ver todos los errores[/dim]")
        return
    if subprocess.run(["systemctl", "is-active", "--quiet", "nginx"], check=False).returncode != 0:
        return
    r2 = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True, check=False)
    if r2.returncode == 0:
        console.print("[green]  ✓ Nginx recargado[/green]")
    else:
        console.print("[yellow]  ⚠ No se pudo recargar Nginx[/yellow]")
