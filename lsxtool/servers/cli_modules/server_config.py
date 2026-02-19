"""
Generación y escritura de configuración YAML para servidores.
Workspace en modo import: .lsxtool/workspaces/{provider}/servers/web/{service}/{env}/{server_name}/
La estructura remota se preserva: ej. /etc/nginx/snippets/server/00-core → .../snippets/server/00-core
"""

import os
import re
import subprocess
import yaml
from pathlib import Path
from typing import Optional
from rich.console import Console

# Base del filesystem por servicio (para calcular ruta relativa en el workspace)
SERVICE_BASE_PATHS: dict[str, str] = {
    "nginx": "/etc/nginx",
    "apache": "/etc/apache2",
    "traefik": "/etc/traefik",
}

# nginx.conf canónico de referencia (workspace)
NGINX_CONF_CANONICAL = """# nginx.conf canónico - referencia para import/sync
# Uso: copiar a /etc/nginx/nginx.conf o usar como base

user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections 768;
}

http {
    sendfile on;
    tcp_nopush on;
    types_hash_max_size 2048;
    default_type application/octet-stream;

    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    gzip on;
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/snippets/*.conf;
    include /etc/nginx/sites-enabled/*;
}
"""


def get_default_routes(service: str, include_src: bool = True) -> list[dict]:
    """
    Obtiene las rutas por defecto para un servicio desde sync_routes.
    - include_src=True (managed/bootstrap): incluye src y dest.
    - include_src=False (import): solo dest, label, type, glob; src se define al sincronizar al workspace.
    """
    from .sync_routes import SYNC_ROUTES

    routes = SYNC_ROUTES.get(service, [])
    result = []
    for route in routes:
        route_dict = {
            "label": route.get("label", route.get("src", route["dest"])),
            "type": route["type"],
            "dest": route["dest"],
        }
        if include_src and "src" in route:
            route_dict["src"] = route["src"]
        if "glob" in route:
            route_dict["glob"] = route["glob"]
        result.append(route_dict)
    return result


def _detect_layout(routes: list[dict]) -> str:
    """legacy = solo defaults planos; standard = todos un nivel; mixed = jerarquía variada."""
    if not routes:
        return "legacy"
    srcs = [r.get("src", "") for r in routes if r.get("src")]
    if not srcs:
        return "legacy"
    has_nested = any("/" in s for s in srcs)
    all_flat = all("/" not in s for s in srcs)
    if has_nested and not all_flat:
        return "mixed"
    return "standard" if all_flat else "mixed"


def _detect_scope(routes: list[dict]) -> str:
    """Si hay rutas con varios entornos (dev, qa, prod), scope: global."""
    env_like = {"dev", "qa", "prod"}
    found: set[str] = set()
    for r in routes:
        for part in (r.get("src") or "").split("/"):
            if part in env_like:
                found.add(part)
    return "global" if len(found) > 1 else "single"


def generate_yaml_config(data: dict) -> dict:
    """
    Genera la estructura YAML según el schema.
    - mode import: discovery + workspace.root + preserve_tree + layout + scope.
    - mode managed/bootstrap: routes con src desde SYNC_ROUTES.
    """
    mode = data.get("mode", "managed")
    config = {
        "provider": data["provider"],
        "service": data["service"],
        "environment": data["environment"],
        "mode": mode,
        "target": data["target"],
    }

    # Discovery (solo en modo import); root es la base del servicio, no una ruta
    if mode == "import" and data.get("discovery"):
        discovery = dict(data["discovery"])
        if "root" not in discovery:
            discovery["root"] = SERVICE_BASE_PATHS.get(data["service"], "/etc/nginx")
        config["discovery"] = discovery

    # Routes: en import usar import_routes si existen (workspace creado); si no, defaults sin src
    if mode == "import" and data.get("import_routes"):
        routes = data["import_routes"]
        config["routes"] = routes
        config["layout"] = _detect_layout(routes)
        config["scope"] = _detect_scope(routes)
        # Ruta relativa del workspace bajo .lsxtool (para referencia en sync/normalize)
        config["workspace"] = {
            "root": f"workspaces/{data['provider']}/servers/web/{data['service']}/{data['environment']}/{data['server_name']}",
        }
    else:
        include_src = mode in ("managed", "bootstrap")
        routes = get_default_routes(data["service"], include_src=include_src)
        if routes:
            config["routes"] = routes

    # Pre-sync (opcional)
    if data.get("pre_sync"):
        config["pre_sync"] = data["pre_sync"]

    # Reload (opcional)
    if data.get("reload_cmd"):
        config["reload"] = {"cmd": data["reload_cmd"]}

    return config


def _parse_nginx_includes(command: str, base_path: str = "/etc/nginx") -> list[tuple[str, str]]:
    """
    Ejecuta el comando (ej. nginx -T) y extrae rutas de include.
    Devuelve lista de (dest_abs, src_relative) preservando la estructura completa.
    Regla: nunca colapsar profundidad; src_relative siempre es la ruta completa bajo la base.
    - Incluye absolutos: /etc/nginx/snippets/server/00-core/01-security → rel = snippets/server/00-core/01-security
    - Incluye relativos: snippets/server/00-core/01-security → se normaliza con base → mismo rel
    """
    try:
        out = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    base = base_path.rstrip("/")
    if not base.startswith("/"):
        base = "/" + base

    seen: set[tuple[str, str]] = set()
    for m in re.finditer(r"include\s+(\S+)\s*;", out.stdout or ""):
        raw = m.group(1).strip("'\"").rstrip(";")
        # Si tiene glob, el path es un directorio; si no, es archivo → usar padre
        if "*" in raw:
            path = raw[: raw.index("*")].rstrip("/")
        else:
            path = str(Path(raw).parent)
        path = path.rstrip("/")
        # Incluye relativos: nginx -T puede mostrar "snippets/..." sin /etc/nginx
        if not path.startswith("/"):
            path = f"{base}/{path.lstrip('/')}"
        if not path.startswith(base):
            continue
        # Ruta relativa bajo la base; excluir "." y rutas vacías (ej. /etc/nginx/.)
        rel = path[len(base) :].lstrip("/")
        if not rel or rel == ".":
            continue
        key = (path, rel)
        if key not in seen:
            seen.add(key)
    return sorted(seen, key=lambda x: x[0])


def _collapse_to_top_level_routes(
    parsed: list[tuple[str, str]],
    base_path: str,
    service: str,
) -> list[dict]:
    """
    Reduce las rutas a solo primer nivel (conf.d, snippets, sites-enabled, modules-enabled).
    Sin subdirectorios si el padre tiene preserve_tree: true. YAML mínimo 4-5 routes.
    """
    base = base_path.rstrip("/") or "/etc/nginx"
    if not base.startswith("/"):
        base = "/" + base
    first_segment: dict[str, str] = {}  # segment -> dest_abs (cualquier path bajo ese segment)
    for dest_abs, src_relative in parsed:
        if not src_relative or src_relative == ".":
            continue
        parts = src_relative.split("/")
        seg = parts[0]
        if seg not in first_segment:
            first_segment[seg] = f"{base}/{seg}"
    routes = []
    for seg in sorted(first_segment.keys()):
        dest = first_segment[seg]
        routes.append({
            "label": f"{service}/{seg}",
            "type": "dir",
            "dest": dest,
            "src": seg,
            "preserve_tree": True,
        })
    return routes


def _routes_from_base_path(base_path: str, service: str) -> list[dict]:
    """
    Construye rutas desde el directorio base: un primer nivel por cada subdirectorio existente.
    Usado cuando el usuario indica la ruta de configuración (ej. /etc/nginx) sin discovery.
    """
    base = Path(base_path)
    if not base.exists() or not base.is_dir():
        return _routes_from_sync_routes_for_import(service)
    routes = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            routes.append({
                "label": f"{service}/{d.name}",
                "type": "dir",
                "dest": str(d.resolve()),
                "src": d.name,
                "preserve_tree": True,
            })
    if not routes:
        return _routes_from_sync_routes_for_import(service)
    return routes


def _routes_from_sync_routes_for_import(service: str) -> list[dict]:
    """Rutas por defecto para import: dest + src = último componente del path (ej. conf.d)."""
    from .sync_routes import SYNC_ROUTES
    routes = SYNC_ROUTES.get(service, [])
    result = []
    for r in routes:
        dest = r["dest"]
        src_name = Path(dest).name or dest.strip("/").split("/")[-1] or "config"
        route = {
            "label": r.get("label", src_name),
            "type": r["type"],
            "dest": dest,
            "src": src_name,
        }
        if "glob" in r:
            route["glob"] = r["glob"]
        result.append(route)
    return result


def _chown_workspace_to_effective_user(workspace_dir: Path) -> None:
    """Si se ejecutó con sudo, deja el workspace como dueño al usuario que ejecutó (p. ej. SUDO_USER)."""
    from .provider_config import get_effective_user_and_group
    ug = get_effective_user_and_group()
    if not ug:
        return
    user, group = ug
    try:
        import shutil
        for root, dirs, files in os.walk(workspace_dir, topdown=False):
            for name in files + dirs:
                p = Path(root) / name
                shutil.chown(p, user=user, group=group)
        shutil.chown(workspace_dir, user=user, group=group)
    except (ImportError, OSError):
        try:
            subprocess.run(
                ["chown", "-R", f"{user}:{group}", str(workspace_dir)],
                check=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass


def run_import_discovery_and_create_workspace(
    wizard_data: dict,
    console: Console,
) -> list[dict]:
    """
    Modo import: ejecuta discovery si está configurado, crea workspace y devuelve rutas.
    - Crea .lsxtool/workspaces/{provider}/servers/web/{service}/{env}/{server_name}/
    - Estructura remota preservada: /etc/nginx/snippets/server/00-core → .../snippets/server/00-core
    - Si se ejecutó con sudo, chown al usuario que ejecutó para que pueda escribir.
    """
    provider = wizard_data["provider"]
    service = wizard_data["service"]
    environment = wizard_data["environment"]
    server_name = wizard_data["server_name"]
    discovery = wizard_data.get("discovery") or {}
    # Ruta de configuración en el servidor (ej. /etc/nginx). Prioridad: wizard_data > discovery
    base_path = (
        wizard_data.get("config_path")
        or wizard_data.get("base_path")
        or discovery.get("base_path")
        or SERVICE_BASE_PATHS.get(service, "/etc/nginx")
    )
    if isinstance(base_path, Path):
        base_path = str(base_path)

    workspace_dir = get_workspace_dir(provider, service, environment, server_name)

    # Rutas: 1) discovery con comando (nginx -T), 2) base_path (subdirs del path), 3) defaults
    routes: list[dict] = []
    if discovery.get("method") == "auto" and discovery.get("command"):
        parsed = _parse_nginx_includes(discovery["command"], base_path=base_path)
        if parsed:
            routes = _collapse_to_top_level_routes(parsed, base_path, service)
        else:
            console.print("[dim]No se pudieron extraer rutas del comando; usando rutas desde el path.[/dim]")
    if not routes:
        routes = _routes_from_base_path(base_path, service)
    if not routes:
        routes = _routes_from_sync_routes_for_import(service)
    for r in routes:
        if "preserve_tree" not in r:
            r["preserve_tree"] = True

    # Mostrar solo rutas detectadas (lista limpia)
    console.print("\n[bold cyan]Rutas detectadas:[/bold cyan]")
    for r in routes:
        console.print(f"  [dim]{r['dest']}[/dim] → [green]{r['src']}[/green]")

    # Crear workspace y solo directorios de primer nivel (el copy trae el árbol)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    for r in routes:
        (workspace_dir / r["src"]).mkdir(parents=True, exist_ok=True)

    # Copiar contenido remoto → local (sin imprimir cada archivo; devuelve conteo)
    num_dirs, num_files = _copy_remote_to_workspace(routes, workspace_dir, console)

    # nginx.conf canónico de referencia en el workspace
    _write_canonical_nginx_conf(workspace_dir)

    # Que el usuario que ejecutó pueda escribir (p. ej. si se usó sudo)
    _chown_workspace_to_effective_user(workspace_dir)

    # Resumen final
    console.print(f"\n[green]✓ Sincronización completada ({num_dirs} directorios, {num_files} archivos)[/green]")
    console.print(f"[green]✓ Workspace:[/green] [bold]{workspace_dir}[/bold]")

    return routes


def _write_canonical_nginx_conf(workspace_dir: Path) -> None:
    """Escribe nginx.conf canónico de referencia en la raíz del workspace."""
    path = workspace_dir / "nginx.conf"
    path.write_text(NGINX_CONF_CANONICAL, encoding="utf-8")


def _copy_remote_to_workspace(
    routes: list[dict], workspace_dir: Path, console: Console
) -> tuple[int, int]:
    """
    Copia el contenido de cada ruta remota (dest) al workspace (src).
    No imprime cada archivo; devuelve (num_directorios, num_archivos) para el resumen final.
    """
    import shutil
    to_copy = [r for r in routes if "/" not in r.get("src", "") and r.get("src") not in ("", ".")]
    if not to_copy:
        to_copy = routes
    errors = []
    copied_dirs = 0
    for r in to_copy:
        src_path = Path(r["dest"])
        dst_path = workspace_dir / r["src"]
        if not src_path.exists():
            continue
        if not src_path.is_dir():
            try:
                shutil.copy2(src_path, dst_path)
            except (OSError, PermissionError) as e:
                errors.append((str(src_path), str(e)))
            continue
        try:
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True, symlinks=True)
            copied_dirs += 1
        except PermissionError as e:
            errors.append((str(src_path), str(e)))
        except OSError as e:
            errors.append((str(src_path), str(e)))
    if errors:
        console.print("[yellow]⚠ No se pudo copiar alguna ruta (¿ejecutar con sudo?):[/yellow]")
        for path, err in errors[:3]:
            console.print(f"  [dim]{path}:[/dim] {err}")
        if len(errors) > 3:
            console.print(f"  [dim]... y {len(errors) - 3} más.[/dim]")
    num_files = sum(len(files) for _root, _dirs, files in os.walk(workspace_dir))
    return (copied_dirs, num_files)


def get_workspace_dir(
    provider: str,
    service: str,
    environment: str,
    server_name: str,
) -> Path:
    """
    Directorio del workspace local para modo import.
    .lsxtool/workspaces/{provider}/servers/web/{service}/{env}/{server_name}/
    """
    from .provider_config import get_lsxtool_base_dir
    base = get_lsxtool_base_dir()
    return base / "workspaces" / provider / "servers" / "web" / service / environment / server_name


def list_configured_servers() -> list[dict]:
    """
    Lista los servidores dados de alta: escanea .lsxtool/providers/{provider}/servers/{service}/{env}/*.yml.
    Devuelve lista de {provider, service, environment, server_name, yaml_path}.
    """
    from .provider_config import get_lsxtool_base_dir
    base = get_lsxtool_base_dir()
    providers_dir = base / "providers"
    if not providers_dir.exists():
        return []
    result = []
    for provider in sorted(providers_dir.iterdir()):
        if not provider.is_dir():
            continue
        servers_dir = provider / "servers"
        if not servers_dir.exists():
            continue
        for service in sorted(servers_dir.iterdir()):
            if not service.is_dir():
                continue
            for env in sorted(service.iterdir()):
                if not env.is_dir():
                    continue
                for yml in env.glob("*.yml"):
                    if yml.name.startswith("."):
                        continue
                    result.append({
                        "provider": provider.name,
                        "service": service.name,
                        "environment": env.name,
                        "server_name": yml.stem,
                        "yaml_path": yml,
                    })
    return result


def get_config_path(
    provider: str,
    service: str,
    environment: str,
    server_name: str,
) -> Path:
    """
    Ruta donde se escribe el YAML generado por servers add.
    En dev: proyecto/.lsxtool/providers/{provider}/servers/{service}/{env}/{name}.yml
    En prod: effective_home/.lsxtool/providers/... (con sudo se usa SUDO_USER, no /root).
    """
    from .provider_config import get_lsxtool_base_dir
    base = get_lsxtool_base_dir()
    config_dir = base / "providers" / provider / "servers" / service / environment
    return config_dir / f"{server_name}.yml"


def write_config_file(
    config: dict,
    config_path: Path,
    console: Console,
) -> Path:
    """Escribe el archivo YAML de configuración."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    return config_path
