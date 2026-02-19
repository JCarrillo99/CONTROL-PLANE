"""
Orquestación de sistema para bootstrap: usuarios, grupos, filesystem y permisos.
Garantiza /var/www/<provider>/<env>/<slug> y /var/log/<provider>/<env>/<slug>
con ownership y permisos correctos (group = owner, technical_user:group, chmod 2775).

Las operaciones que crean grupos o cambian ownership pueden requerir ejecución con sudo.
"""

import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple
from rich.console import Console
from rich.panel import Panel


def _run(cmd: list, console: Optional[Console] = None, capture: bool = True) -> Tuple[bool, str]:
    """Ejecuta comando; retorna (éxito, salida)."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=30,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return (r.returncode == 0, out.strip())
    except Exception as e:
        if console:
            console.print(f"[red]Error ejecutando {cmd}: {e}[/red]")
        return (False, str(e))


def group_exists(group_name: str) -> bool:
    """Comprueba si el grupo existe en el sistema."""
    ok, _ = _run(["getent", "group", group_name], capture=True)
    return ok


def ensure_group(group_name: str, console: Optional[Console] = None) -> bool:
    """
    Crea el grupo en el sistema si no existe.
    Requiere privilegios elevados (sudo) para groupadd.
    """
    if group_exists(group_name):
        if console:
            console.print(f"  [dim]Grupo [cyan]{group_name}[/cyan] ya existe[/dim]")
        return True
    ok, out = _run(["groupadd", group_name], console=console, capture=False)
    if ok and console:
        console.print(f"  [green]✓[/green] Grupo [cyan]{group_name}[/cyan] creado")
    elif not ok and console:
        console.print(f"  [red]❌ No se pudo crear el grupo {group_name}[/red]")
        console.print(f"  [dim]Ejecuta con sudo o crea el grupo manualmente: sudo groupadd {group_name}[/dim]")
    return ok


def user_exists(username: str) -> bool:
    """Comprueba si el usuario existe en el sistema."""
    ok, _ = _run(["getent", "passwd", username], capture=True)
    return ok


def ensure_user(username: str, console: Optional[Console] = None) -> bool:
    """
    Crea el usuario en el sistema si no existe.
    Usa useradd -m -s /bin/bash para un usuario técnico con directorio home.
    Requiere privilegios elevados (sudo) para useradd.
    """
    if user_exists(username):
        if console:
            console.print(f"  [dim]Usuario [cyan]{username}[/cyan] ya existe[/dim]")
        return True
    ok, out = _run(["useradd", "-m", "-s", "/bin/bash", username], console=console, capture=False)
    if ok and console:
        console.print(f"  [green]✓[/green] Usuario [cyan]{username}[/cyan] creado")
    elif not ok and console:
        console.print(f"  [red]❌ No se pudo crear el usuario {username}[/red]")
        console.print(f"  [dim]Ejecuta con sudo: sudo useradd -m -s /bin/bash {username}[/dim]")
    return ok


def user_in_group(user: str, group_name: str) -> bool:
    """Comprueba si el usuario pertenece al grupo."""
    ok, out = _run(["id", "-nG", user], capture=True)
    if not ok:
        return False
    groups = out.split()
    return group_name in groups


def ensure_user_in_group(user: str, group_name: str, console: Optional[Console] = None) -> bool:
    """
    Añade el usuario al grupo si no pertenece ya.
    Requiere privilegios elevados (sudo) para usermod.
    """
    if user_in_group(user, group_name):
        if console:
            console.print(f"  [dim]Usuario [cyan]{user}[/cyan] ya está en el grupo [cyan]{group_name}[/cyan][/dim]")
        return True
    ok, out = _run(["usermod", "-aG", group_name, user], console=console, capture=False)
    if ok and console:
        console.print(f"  [green]✓[/green] Usuario [cyan]{user}[/cyan] añadido al grupo [cyan]{group_name}[/cyan]")
    elif not ok and console:
        console.print(f"  [yellow]⚠[/yellow] No se pudo añadir {user} al grupo {group_name}")
        console.print(f"  [dim]Ejecuta con sudo: sudo usermod -aG {group_name} {user}[/dim]")
    return ok


def ensure_fs_dirs(
    provider: str,
    env: str,
    slug: str,
    owner_user: str,
    owner_group: str,
    console: Optional[Console] = None,
    dry_run: bool = False,
) -> bool:
    """
    Crea /var/www/<provider>/<env>/<slug> y /var/log/<provider>/<env>/<slug>,
    asigna ownership owner_user:owner_group y chmod 2775 (SGID para herencia de grupo).

    provider, env, slug deben estar en formato normalizado (lowercase, sin espacios).
    """
    www_root = Path("/var/www") / provider.lower() / env.lower() / slug.lower()
    log_root = Path("/var/log") / provider.lower() / env.lower() / slug.lower()
    dirs = [www_root, log_root]

    if dry_run:
        if console:
            for d in dirs:
                console.print(f"  [dim](dry-run) Crear: {d}[/dim]")
                console.print(f"  [dim](dry-run) chown -R {owner_user}:{owner_group} {d}[/dim]")
                console.print(f"  [dim](dry-run) chmod -R 2775 {d}[/dim]")
        return True

    all_ok = True
    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            if console:
                console.print(f"  [green]✓[/green] Directorio: [cyan]{d}[/cyan]")
        except PermissionError:
            if console:
                console.print(f"  [red]❌ Sin permisos para crear {d}[/red]")
                console.print(f"  [dim]Crea manualmente: sudo mkdir -p {d}[/dim]")
            all_ok = False
            continue
        except Exception as e:
            if console:
                console.print(f"  [red]❌ Error creando {d}: {e}[/red]")
            all_ok = False
            continue

        # chown -R user:group (puede requerir sudo)
        ok, _ = _run(["chown", "-R", f"{owner_user}:{owner_group}", str(d)], console=None)
        if not ok:
            if console:
                console.print(f"  [yellow]⚠[/yellow] No se pudo chown {d} (¿ejecutar con sudo?)[/yellow]")
                console.print(f"  [dim]sudo chown -R {owner_user}:{owner_group} {d}[/dim]")
            all_ok = False
        elif console:
            console.print(f"  [green]✓[/green] Ownership [cyan]{owner_user}:{owner_group}[/cyan] en {d}")

        # chmod -R 2775 (SGID)
        ok, _ = _run(["chmod", "-R", "2775", str(d)], console=None)
        if not ok:
            if console:
                console.print(f"  [yellow]⚠[/yellow] No se pudo chmod 2775 en {d}[/yellow]")
            all_ok = False
        elif console:
            console.print(f"  [green]✓[/green] Permisos 2775 (SGID) en {d}")

    return all_ok


def run_bootstrap_orchestration(
    provider: str,
    env: str,
    slug: str,
    owner: str,
    technical_user: Optional[str],
    base_dir: Path,
    console: Console,
    dry_run: bool = False,
) -> bool:
    """
    Ejecuta la orquestación completa para un dominio:
    1) Asegura grupo = owner
    2) Asegura technical_user en grupo (o usuario actual)
    3) Crea /var/www y /var/log y aplica ownership y permisos.

    technical_user: usuario técnico para ownership; si None, se usa el usuario actual.
    """
    console.print(Panel.fit(
        "[bold cyan]Orquestación de sistema[/bold cyan]\n"
        f"[dim]provider=[/dim] {provider} [dim]env=[/dim] {env} [dim]slug=[/dim] {slug}\n"
        f"[dim]owner (grupo)=[/dim] {owner} [dim]usuario técnico=[/dim] {technical_user or '(actual)'}",
        border_style="cyan",
    ))

    group_name = owner
    user_for_ownership = technical_user or os.environ.get("USER", "root")

    if not ensure_group(group_name, console):
        if not dry_run:
            console.print("[yellow]⚠ Continuando sin grupo; los directorios se crearán con permisos por defecto.[/yellow]")

    if not dry_run:
        if technical_user:
            ensure_user(user_for_ownership, console)
        ensure_user_in_group(user_for_ownership, group_name, console)

    return ensure_fs_dirs(
        provider,
        env,
        slug,
        user_for_ownership,
        group_name,
        console,
        dry_run=dry_run,
    )
